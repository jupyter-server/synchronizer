from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.handler import ExtensionHandlerMixin
from tornado.web import HTTPError


class SynchronizerHandler(ExtensionHandlerMixin, APIHandler):
    async def post(self):
        """Trigger the synchronizer"""
        try:
            await self.extensionapp.sync_managers()
        except Exception as err:
            raise HTTPError(500, log_message=str(err))


handlers = [
    (r"/api/sync", SynchronizerHandler),
]
