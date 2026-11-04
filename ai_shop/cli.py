import argparse
import json
import os
from pathlib import Path

from .assistant import Assistant
from .downloader import download, MODEL
from .errors import AIShopError
from .knowledge import KnowledgeBase


def main():
    parser = argparse.ArgumentParser(prog='ai-shop', description='Self-hosted local-model website assistant')
    sub = parser.add_subparsers(dest='command', required=True)
    model = sub.add_parser('download-model'); model.add_argument('--output')
    serve = sub.add_parser('serve'); serve.add_argument('--config', help='Multi-site JSON; omit to use AI_SHOP_SITE_* environment variables')
    serve.add_argument('--host', default='127.0.0.1'); serve.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8090')))
    serve.add_argument('--data-dir', default=os.environ.get('AI_SHOP_DATA_DIR', 'private'))
    serve.add_argument('--preload', action='store_true', help='Load the model before accepting requests; fail startup if it is unavailable')
    for name in ('index', 'chat', 'pending', 'approve', 'forget'):
        command = sub.add_parser(name)
        command.add_argument('--site', required=True); command.add_argument('--origin', required=True)
        command.add_argument('--data-dir', default='private')
        if name == 'index':
            command.add_argument('--feed'); command.add_argument('--snapshot')
            command.add_argument('--brand', default='Store'); command.add_argument('--max-pages', type=int, default=25)
            command.add_argument('--currency', default='IRT'); command.add_argument('--decimals', type=int, default=0)
        if name == 'approve':
            command.add_argument('--id', required=True); command.add_argument('--source-url', required=True)
            command.add_argument('--excerpt-file', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'download-model':
            destination = args.output or os.environ.get('AI_SHOP_MODEL_PATH') or str(Path(os.environ.get('AI_SHOP_MODEL_DIR', 'models')) / MODEL['filename'])
            download(destination); return
        if args.command == 'serve':
            from .service import serve
            serve(args.config, host=args.host, port=args.port, data_dir=args.data_dir, preload=args.preload); return
        knowledge = KnowledgeBase(Path(args.data_dir) / 'knowledge.sqlite3')
        assistant = Assistant(site_id=args.site, origin=args.origin, knowledge=knowledge)
        if args.command == 'index':
            if args.snapshot: result = assistant.sync_public_data(json.loads(Path(args.snapshot).read_text(encoding='utf-8')))
            else: result = assistant.index_public_site(brand=args.brand, feed_url=args.feed, max_pages=args.max_pages,
                                                       currency={'code': args.currency, 'decimals': args.decimals, 'label': args.currency})
            print(json.dumps({'products': len(result['products']), 'pages': len(result['pages'])}))
        elif args.command == 'pending':
            print(json.dumps(knowledge.pending(args.site), ensure_ascii=False, indent=2))
        elif args.command == 'approve':
            knowledge.approve(args.site, args.id, excerpt=Path(args.excerpt_file).read_text(encoding='utf-8'), source_url=args.source_url)
            print('Public-source learning approved.')
        elif args.command == 'forget':
            if input('Delete the reviewed and pending learning for this site? Type YES: ') == 'YES':
                knowledge.forget(args.site); print('Learning removed for this site.')
        elif args.command == 'chat':
            history = []
            while True:
                try: message = input('You: ').strip()
                except EOFError: break
                if not message: break
                result = assistant.answer(message, history)
                print('Assistant:', result['reply'])
                history = (history + [{'role': 'user', 'content': message}, {'role': 'assistant', 'content': result['reply'][:1400]}])[-12:]
    except (AIShopError, OSError, ValueError) as error:
        parser.exit(1, 'AI-Shop: ' + (error.code if isinstance(error, AIShopError) else 'Check the local files and configuration.') + '\n')
