"""Opt-in local settings surface for the existing Flask app; no token is returned."""
from flask import Response, jsonify, request
if __package__ and __package__.startswith('agents.legal_agent'):
    from .meterless import MeterlessRuntime,MeterlessSettings,RuntimeConfig,auto_detect
else:
    from tools.meterless import MeterlessRuntime,MeterlessSettings,RuntimeConfig,auto_detect

HTML='''<!doctype html><meta charset="utf-8"><title>Meterless Runtime</title>
<h1>Meterless Runtime</h1><p id="status">Check connection or auto detect a local runtime.</p>
<label>Base URL <input id="base" value="http://127.0.0.1:8088/v1"></label><br>
<label>Connect link <input id="connect" type="password" autocomplete="off"></label><br>
<label>Runtime token <input id="token" type="password" autocomplete="off"></label><br>
<label>Routing mode <select id="model"><option>meterless/auto</option></select></label><br>
<button id="save">Save and check</button><button id="detect">Auto Detect</button><button id="check">Check connection</button>
<script>
const $=id=>document.getElementById(id);
async function run(action){
 try{
 let path='/providers/meterless';let options={};
 if(action!=='check'){
 path+='/'+action;options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(action==='configure'?{base_url:$('base').value,connect_link:$('connect').value,meterless_runtime_token:$('token').value,model:$('model').value}:{})};
 }
 const response=await fetch(path,options);const result=await response.json();
 $('token').value='';$('connect').value='';
 $('status').textContent=result.status==='unauthorized'?'Unauthorized. Paste the real runtime token.':result.status||'Request failed';
 if(result.base_url)$('base').value=result.base_url;
 if(result.models&&result.models.length){$('model').replaceChildren(...result.models.map(id=>{let o=document.createElement('option');o.textContent=id;o.value=id;return o;}));}
 }catch(e){$('status').textContent='Connection unavailable';}
}
$('save').onclick=()=>run('configure');$('detect').onclick=()=>run('detect');$('check').onclick=()=>run('check');
</script>'''


def install_settings_routes(app,*,settings=None,transport=None):
    settings=settings or MeterlessSettings()
    def guard():
        if request.remote_addr not in {'127.0.0.1','::1'}:return jsonify(error='local_settings_only'),403
        if request.headers.get('Origin') and request.headers['Origin']!=request.host_url.rstrip('/'):
            return jsonify(error='origin_not_allowed'),403
        if request.method=='POST' and not request.is_json:return jsonify(error='json_required'),415
    @app.get('/providers/meterless/settings')
    def meterless_page():
        blocked=guard()
        return blocked or Response(HTML,mimetype='text/html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'})
    @app.get('/providers/meterless')
    def meterless_status():
        blocked=guard()
        if blocked:return blocked
        return jsonify(MeterlessRuntime(RuntimeConfig.from_env(settings=settings),transport=transport).probe())
    @app.post('/providers/meterless/configure')
    def meterless_configure():
        blocked=guard()
        if blocked:return blocked
        data=request.get_json()
        settings.save(base_url=data.get('connect_link') or data.get('base_url',''),
                      token=data.get('meterless_runtime_token') or None,model=data.get('model'))
        saved=settings.load()
        runtime=MeterlessRuntime(RuntimeConfig(saved['base_url'],saved.get('meterless_runtime_token',''),saved['model']),transport=transport)
        return jsonify(runtime.probe())
    @app.post('/providers/meterless/detect')
    def meterless_detect():
        blocked=guard()
        if blocked:return blocked
        return jsonify(auto_detect(token=RuntimeConfig.from_env(settings=settings).token,settings=settings,transport=transport))
