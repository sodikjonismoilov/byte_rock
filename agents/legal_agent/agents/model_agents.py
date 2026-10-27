if __package__ and __package__.startswith("agents.legal_agent"):
    from ..context import agent_context, compact_finding
else:
    from context import agent_context, compact_finding
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import ResearchPlan, ResearchDraft, CriticReport, ResearchQuestion
else:
    from models.schemas import ResearchPlan, ResearchDraft, CriticReport, ResearchQuestion
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..tools.execution import ExecutionStopped
else:
    from tools.execution import ExecutionStopped


class ModelAgents:
    def _pack(self,task,context,payload,base_keys,**context_options):
        """Reserve payload space for task/draft fields without enlarging hard limits."""
        import json,os
        if __package__ and __package__.startswith('agents.legal_agent'):
            from ..tools.llm import request_size,request_budget
        else:
            from tools.llm import request_size,request_budget
        cap=request_budget()
        schema={'planner':ResearchPlan,'researcher':ResearchDraft,'independent_critic':CriticReport}[payload['role']]
        model=getattr(getattr(self.adapter,'adapter',self.adapter),'model','configured')
        if not isinstance(model,str):model='configured'
        extras={k:v for k,v in payload.items() if k not in base_keys}
        for _ in range(3):
            size=request_size(schema,payload,model)
            if size<=cap:return payload
            budget=payload['selection']['max_bytes']-(size-cap)-512
            if budget<1024:raise ExecutionStopped('Mandatory model context exceeds payload budget')
            payload={**agent_context(task,context,max_bytes=budget,**context_options),**extras}
        raise ExecutionStopped('Mandatory model context exceeds payload budget')

    def __init__(self, adapter):
        self.adapter = adapter
        self.prior_draft = None
        self.feedback = None
        self.retrieved = {}
        self.required_followups = []
        self.search_actions = set()
        self.external_limits = []
        self.truncation_retried = False

    def plan(self, task, context, prior_feedback=None, revision=0, reasoning_mode='llm'):
        self.feedback = prior_feedback
        payload = agent_context(task,context,feedback=prior_feedback)
        base_keys=set(payload)
        payload['role'] = 'planner'
        payload['revision'] = revision
        payload['available_tools'] = ['legal_search','evidence_review','request_external']
        payload['tool_descriptions'] = {
            'legal_search':'Execute keyword retrieval over the curated legal catalog. Returns original official excerpts where available, exact authority IDs, identifiers, jurisdiction, URLs and version limits. Required before interpreting housing duties; summaries alone are not statutory text.',
            'evidence_review':'Compare accepted official records, statuses, scope and contradictions. Cannot retrieve law or convert memories/filings into violations.',
            'request_external':'Ask the team for unavailable records or operative historical law. Not an executed data retrieval.'}
        payload['substantive_topics'] = substantive_topics(task,context)
        payload['required_followups'] = [q.model_dump(mode='json') for q in self.required_followups]
        payload['planning_requirements'] = 'Prioritize the substantive concerns actually present in accepted records (e.g. boilers, heat, repairs, permits), not just record limitations. Select at least one focused legal_search. Use only accepted evidence IDs; memory IDs belong only in memory_ids. At most four compact tasks. An interpretation task should depend on its legal_search task IDs. Return any valid DAG order; runtime orders it. Dependencies must reference question_ids in this plan or supplied required_followups, never finding IDs or old tasks. On revision address the required follow-up with changed activity.'
        if self.prior_draft:
            payload['prior_research_tasks'] = self.prior_plan.model_dump(mode='json')
        payload=self._pack(task,context,payload,base_keys,feedback=prior_feedback)
        plan = self.adapter.complete(ResearchPlan,payload)
        if plan.task_id != task.task_id or not plan.questions or len(plan.questions)>10:
            raise ExecutionStopped('Invalid research plan scope')
        valid_evidence={e.evidence_id for e in context.evidence}
        valid_memory={m.get('memory_id') for m in context.untrusted_memory}
        for q in plan.questions:
            if not set(q.evidence_ids)<=valid_evidence or not set(q.memory_ids)<=valid_memory:
                raise ExecutionStopped('Plan cites references outside their evidence or memory registry')
        # Retrieval is an enforced research precondition, not a deterministic reasoning fallback.
        additions=list(self.required_followups)
        if not any(q.recommended_tool=='legal_search' for q in plan.questions) and not additions:
            topics=substantive_topics(task,context)
            additions=[ResearchQuestion(question_id='runtime-authority-lookup',prompt='NYC housing duties '+ ' '.join(topics),
                focus_topics=topics,recommended_tool='legal_search',evidence_ids=sorted(valid_evidence))]
        known_ids={q.question_id for q in plan.questions}
        for q in additions:
            if not any(x.prompt==q.prompt and x.recommended_tool==q.recommended_tool for x in plan.questions):
                q=q.model_copy(deep=True)
                while q.question_id in known_ids:q.question_id+='-next'
                known_ids.add(q.question_id);plan.questions.append(q)
        if additions:plan.notes.append('Runtime requires executed authority lookup/follow-up; this does not validate any proposed conclusion.')
        if len(plan.questions)>10:raise ExecutionStopped('Research plan exceeds task budget')
        ids = [q.question_id for q in plan.questions]
        if len(ids)!=len(set(ids)):
            raise ExecutionStopped('Plan dependencies must be unique, acyclic and ordered')
        pending=list(plan.questions);ordered=[];completed=set()
        while pending:
            ready=[q for q in pending if set(q.dependencies)<=completed]
            if not ready:
                raise ExecutionStopped('Plan dependencies must be unique, acyclic and ordered')
            for q in ready:
                pending.remove(q);ordered.append(q);completed.add(q.question_id)
        plan.questions=ordered
        plan.revision, plan.reasoning_mode = revision, reasoning_mode
        if prior_feedback and hasattr(self,'prior_plan'):
            old = {(q.prompt,tuple(q.focus_topics),q.recommended_tool) for q in self.prior_plan.questions}
            new = {(q.prompt,tuple(q.focus_topics),q.recommended_tool) for q in plan.questions}
            if old == new:
                raise ExecutionStopped('Critic revision did not change research activity')
        self.prior_plan = plan
        return plan

    def research(self, task, context, plan, search_tool, reasoning_mode='llm'):
        hits = dict(self.retrieved)
        external = []
        for q in plan.questions:
            if q.recommended_tool == 'legal_search':
                query=' '.join([q.prompt,*q.focus_topics])
                import re
                if self.external_limits and re.search(r'historic|operative|as of|in effect|effective.*date',query,re.I):
                    external.extend(self.external_limits)
                    if getattr(search_tool,'budget',None):search_tool.budget.trace.emit('research.search_skipped',reason='historical_version_unavailable')
                    continue
                for hit in search_tool.search(query,limit=8):
                    hits[hit.source.id] = hit
                self.search_actions.add(query)
            elif q.recommended_tool == 'request_external':
                external.append(q.prompt)
        affected = {id for issue in self.feedback.issues for id in issue.finding_ids} if self.feedback else set()
        retained = [f for f in self.prior_draft.findings if f.finding_id not in affected] if self.prior_draft and affected else []
        if retained:
            for hit in self.prior_draft.retrieved_sources:
                hits.setdefault(hit.source.id,hit)
        wanted = set(e for q in plan.questions for e in q.evidence_ids)
        payload = agent_context(task,context,evidence_ids=wanted or None,findings=retained,feedback=self.feedback,sources=[h.source for h in hits.values()])
        self.retrieved.update(hits)
        base_keys=set(payload)
        payload.update(role='researcher',plan=plan.model_dump(mode='json'),external_requests=external)
        if __package__ and __package__.startswith('agents.legal_agent'):
            from .scope import categories
        else:
            from agents.scope import categories
        payload['required_coverage_categories']=categories(task)
        for source in payload['authorities']:
            if source.get('excerpt') and source.get('authority_type')=='agency_guidance':
                quote=source['excerpt'].split('. ')[0]+('.' if '. ' in source['excerpt'] else '')
                payload['citation_selection_example']={'statement':'','claim_scope':'current_guidance','citations':[{'authority_id':source['id'],'supporting_quote':quote}]}
                break
        payload['citation_selection_policy']='Select citations[].authority_id only from provided authority IDs and copy supporting_quote from that source excerpt. Do not generate source_ids, identifiers, titles, URLs or provenance; runtime fills them. Keep output concise and omit empty optional fields. Quote one complete sentence rather than duplicating an entire multi-sentence excerpt. For current_guidance/statute_text source-text quotations leave statement empty and select the exact quote once; runtime formats the attribution, then the Critic independently verifies it. Do not duplicate quotes in statement. Use explicit statement only for an interpretation, never disguise historical liability as current guidance. Historical application is a distinct unverified interpretation unless separately established.'
        payload['output_budget']='Return at most THREE prioritized observations total, not one per coverage category. Focus on supported substantive housing concerns. Each summary at most 20 words; cite at most two relevant evidence IDs and one short complete source sentence per claim. Do not duplicate records, evidence_kinds, evidence_ids_used, source metadata or excerpts outside supporting_quote. Omit empty optional fields. Entire JSON must fit 2048 tokens. Other coverage remains explicitly deferred, never negative evidence.'
        payload['interpretation_requirements']='Use a required_coverage_categories label for each observation. Prioritize substantive boiler/heat/repair concerns supported by accepted records. Unselected categories remain gaps for the global Planner, not additional findings. Evidence IDs refer only to provided accepted records; authority_id only to retrieved authorities; memory_ids are untrusted context. Select exact supporting quotes from excerpt-backed sources, never catalog summaries. Preserve historical and property applicability limits. No definite liability or claim that administrative records prove unsafe current conditions.'
        payload=self._pack(task,context,payload,base_keys,evidence_ids=wanted or None,findings=retained,feedback=self.feedback,sources=[h.source for h in hits.values()])
        if __package__ and __package__.startswith('agents.legal_agent'):
            from ..tools.llm import ModelTruncated
        else:
            from tools.llm import ModelTruncated
        try:
            draft = self.adapter.complete(ResearchDraft,payload)
        except ModelTruncated:
            if self.truncation_retried:raise
            self.truncation_retried=True
            budget=getattr(self.adapter,'budget',None)
            if budget:budget.trace.emit('research.truncation_retry',attempt=1,observation_limit=1)
            payload['observation_limit']=1
            payload['output_budget']='Truncation retry, final attempt: return ONE prioritized observation, summary at most 15 words, at most two evidence IDs and ONE concise canonical citation with a short exact source sentence. Omit empty optional fields and duplicated records. Return complete JSON; all other categories remain deferred.'
            payload=self._pack(task,context,payload,base_keys,evidence_ids=wanted or None,findings=retained,feedback=self.feedback,sources=[h.source for h in hits.values()])
            draft = self.adapter.complete(ResearchDraft,payload)
        if draft.task_id != task.task_id:
            raise ExecutionStopped('Research draft task mismatch')
        # Authoritative retrieval comes from executed tools, never from model output.
        draft.retrieved_sources = list(hits.values())
        draft.plan_revision, draft.reasoning_mode = plan.revision, reasoning_mode
        if retained:
            retained_ids = {f.finding_id for f in retained}
            draft.findings = retained + [f for f in draft.findings if f.finding_id not in retained_ids]
        records={e.evidence_id:e for e in context.evidence}
        draft.evidence_ids_used=list(dict.fromkeys(eid for f in draft.findings for eid in f.evidence_ids))
        for f in draft.findings:
            f.evidence_kinds=list(dict.fromkeys(records[eid].kind for eid in f.evidence_ids if eid in records))
            f.follow_up_tasks.extend(external)
        deferred=set(categories(task))-{f.issue for f in draft.findings}
        if deferred:draft.caveats.append('Prioritized legal observations only; global coverage deferred: '+', '.join(sorted(deferred)))
        if __package__ and __package__.startswith('agents.legal_agent'):
            from ..citations import ground_draft
        else:
            from citations import ground_draft
        draft=ground_draft(draft,{sid:h.source for sid,h in hits.items()},as_of=context.as_of)
        draft.caveats=list(dict.fromkeys([*draft.caveats,*self.external_limits]))
        self.prior_draft = draft
        return draft

    def critique(self, task, context, draft, search_tool, reasoning_mode='llm'):
        # The legal Critic only needs the records the draft actually cites; all others stay in the registry.
        payload = agent_context(task,context,evidence_ids=draft.evidence_ids_used,sources=[h.source for h in draft.retrieved_sources])
        base_keys=set(payload)
        payload['role'] = 'independent_critic'
        payload['review_requirements']='Check support independently from the original excerpt, not the grounding flags or canonical ID. A narrowly attributed exact current-guidance quote is not a historical application; historical liability still needs independent operative-law/property verification. For a recoverable missing authority/citation issue, specify recommended_agent_or_tool=legal_search, recoverable=true and a concrete follow_up_query. Do not claim a legal search occurred unless an authority was supplied. Missing current/historical agency facts require request_external, not repetitive legal_search. Memory IDs can appear only in memory_ids; flag them as untrusted context, never evidence. Review only legal authority identity, quotation support, applicability and evidence-to-claim dependencies. Global source coverage, task scheduling and property matching belong to the global Planner and root Critic; preserve their decisions. Keep outputs compact. Return one JSON object whose top-level fields are task_id (copy the payload task_id), outcome (PASS, REVISE, BLOCKED or INCONCLUSIVE), issues, revision_instructions.'
        payload['draft'] = {'task_id':draft.task_id,'plan_revision':draft.plan_revision,
            'findings':[compact_finding(f) for f in draft.findings],'evidence_ids_used':draft.evidence_ids_used,
            'retrieved_source_ids':[s['id'] for s in payload['authorities']],
            'caveats':draft.caveats,'reasoning_mode':draft.reasoning_mode}
        payload=self._pack(task,context,payload,base_keys,evidence_ids=draft.evidence_ids_used,sources=[h.source for h in draft.retrieved_sources])
        report = self.adapter.complete(CriticReport,payload)
        if report.task_id != task.task_id:
            raise ExecutionStopped('Critic task mismatch')
        report.reasoning_mode = reasoning_mode
        return report


    def queue_followups(self, task, context, report, search_tool, revision):
        """Execute new, bounded Critic-directed lookups before requesting revised reasoning."""
        legal_codes={'unsupported_legal_conclusion','uncited_legal_conclusion','citation_identifier_mismatch','wrong_topic_source','claim_support_unverified',
            'missing_legal_authority','missing_authority','missing_authority_text','unverified_quotation'}
        evidence_codes={'unknown_evidence','invalid_property_dependency','false_evidence_classification','incomplete_scope'}
        questions=[]
        for issue in sorted(report.issues,key=lambda i:(0 if i.code in legal_codes or i.follow_up_query else 1,i.priority)):
            import re
            historical=issue.code in {'historical_applicability_unverified'} or bool(re.search(r'historic|operative|as of|in effect|effective.*date', (issue.follow_up_query or '')+' '+issue.code+' '+issue.message+' '+issue.required_correction,re.I))
            if historical and not any(h.source.excerpt_provenance.get('historical_version_verified') for h in self.retrieved.values()):
                limitation='Historical applicability cannot be established by this catalog; obtain operative incident-date law externally. Current guidance is not historical liability evidence.'
                if limitation not in self.external_limits:self.external_limits.append(limitation)
                budget=getattr(search_tool,'budget',None)
                if budget:budget.trace.emit('research.external_gap',reason='historical_version_unavailable',issue_code=issue.code)
                continue
            if issue.recommended_agent_or_tool not in {'legal_search','evidence_review'}:continue
            if not (issue.code in legal_codes|evidence_codes or issue.follow_up_query and issue.recommended_agent_or_tool=='legal_search'):continue
            tool='evidence_review' if issue.code in evidence_codes and not issue.follow_up_query else 'legal_search'
            topics=substantive_topics(task,context)
            query=issue.follow_up_query or ('Verify exact legal authority identifiers and source text '+ ' '.join(topics))
            if tool=='evidence_review':query='Reconcile findings against accepted evidence IDs; discard unknown references: '+', '.join(issue.finding_ids)
            # Exact repeats cannot manufacture a revision or consume repeated calls.
            if query in self.search_actions:continue
            self.search_actions.add(query)
            q=ResearchQuestion(question_id=f'critic-follow-up-{revision}-{len(questions)}',prompt=query,
                focus_topics=[],recommended_tool=tool,evidence_ids=[e.evidence_id for e in context.evidence])
            if tool=='legal_search':
                for hit in search_tool.search(query,limit=8):self.retrieved[hit.source.id]=hit
            questions.append(q)
            budget=getattr(search_tool,'budget',None)
            if budget:budget.trace.emit('critic.follow_up',tool=tool,issue_code=issue.code,revision=revision,authority_ids=list(self.retrieved))
            if len(questions)>=2:break
        if self.prior_draft:self.prior_draft.caveats=list(dict.fromkeys([*self.prior_draft.caveats,*self.external_limits]))
        self.required_followups=questions
        return bool(questions)


def substantive_topics(task,context):
    import re
    text=' '.join([*task.issue_types,*[e.description for e in context.evidence]]).lower()
    topics=[topic for topic in ('boiler','heat','hot water','pest','mold','lead','repairs','water','occupancy','permit','certification','registration')
            if re.search(r'\b'+re.escape(topic)+r'\b',text)]
    return topics[:4] or ['housing maintenance','habitability']
