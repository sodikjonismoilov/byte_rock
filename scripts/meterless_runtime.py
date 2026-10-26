"""Local Meterless provider setup. Token/connect link input is hidden, never argv."""
import argparse
import getpass
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.legal_agent.tools.meterless import MeterlessSettings,RuntimeConfig,MeterlessRuntime,auto_detect
from scripts.zetaris_sql import load_env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','detect','configure','text'])
    parser.add_argument('--base-url')
    parser.add_argument('--state-dir',type=Path)
    parser.add_argument('--model',default='meterless/auto')
    parser.add_argument('--prompt',default='Reply with exactly: Meterless connected')
    args=parser.parse_args();load_env();settings=MeterlessSettings()
    if args.action=='configure':
        value=getpass.getpass('Paste connect link (hidden), or Enter to use base URL: ')
        token=None
        if not value:token=getpass.getpass('Runtime token (hidden): ')
        settings.save(base_url=value or args.base_url or 'http://127.0.0.1:8088/v1',token=token,model=args.model)
        print(json.dumps(settings.public()));return
    config=RuntimeConfig.from_env(settings=settings)
    if args.base_url:config=RuntimeConfig(args.base_url,model=args.model)  # Never reuse another origin's token.
    if args.state_dir:
        config=RuntimeConfig(config.base_url,(args.state_dir/'proxy-token').read_text().strip(),args.model)
        settings.save(base_url=config.base_url,token=config.token,model=config.model)
    runtime=MeterlessRuntime(config)
    if args.action=='detect':result=auto_detect(token=config.token,settings=settings)
    elif args.action=='status':result=runtime.probe()
    else:
        result=runtime.probe()
        if result['status']=='online':result={'status':'online','text':runtime.complete_text(args.prompt,model=args.model)}
    print(json.dumps(result))
    if result['status']!='online':raise SystemExit(2)


if __name__=='__main__':
    try:main()
    except SystemExit:raise
    except Exception:
        print('Meterless request failed; private configuration and response bodies withheld.',file=sys.stderr)
        raise SystemExit(1)
