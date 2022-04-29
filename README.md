# Jupyter Server Synchronizer

A Jupyter Server Session Manager that rehydrates and persists kernels and sessions beyond the lifetime of a server.

This is particularly useful for Jupyter Servers running remote kernels and contents.

## Basic usage

Install and enable the extension:

```
pip install jupyter_server_synchronizer

jupyter server extension enable jupyter_server_synchronizer
```

When you start a Jupyter Server, it synchronize all managers before the Web application is started.

```
jupyter server --ServerApp.session_manager_class=jupyter_server_synchronizer.SynchronizerSessionManager
```

To synchronize periodically, enable the auto-synchronizing feature using the `autosync` config option. For example,

```
jupyter server --ServerApp.session_manager_class=jupyter_server_synchronizer.SynchronizerSessionManager --SynchronizerSessionManager.autosync=True
```

Otherwise, you can trigger the synchronization making a `POST` request to the `/api/sync` endpoint.

## Example

Below is a example of running the synchronizer with Jupyter Server talking to a Jupyter Kernel Gateway as its "remote" kernel service provider.

First, start the Kernel Gateway. You'll need to enable the `list_kernels` method. In the example, we are assuming the Kernel Gateway is _not_ multi-tenant; i.e. there is a single KG for a single Jupyter Server. We'll set the port to `9999` to free up `8888` for our Jupyter Server.

```
jupyter kernelgateway \
    --port 9999 \
    --JupyterWebsocketPersonality.list_kernels=True
```

Second, start the Jupyter Server and point it at the Kernel Gateway. Note that we set a `database_filepath` trait in both the `SessionManager` and `SynchronizerExtension` (these paths don't need to be the same). The Synchronize relies on saving/storing of information about Jupyter kernels and sessions in a persistent database. This information is necessary to rehydrate and synchronize.

We'll enable the "autosync" feature to periodically synchronize the server.

```
jupyter lab \
    --gateway-url=http://127.0.0.1:9999 \
    --ServerApp.session_manager_class=jupyter_server_synchronizer.SynchronizerSessionManager
    --SynchronizerSessionManager.database_filepath=jupyter-database.db \
    --SynchronizerSessionManager.autosync=True \
    --SynchronizerSessionManager.log_level=DEBUG
```

Now, let's kill that server:

```
kill -9 $(echo $(pgrep -lf jupyter-lab) | awk '{print $1;}')
```

And restart it to see if the kernels rehydrate and begin synchronizing again.

```
jupyter lab \
    --gateway-url=http://127.0.0.1:9999 \
    --ServerApp.session_manager_class=jupyter_server_synchronizer.SynchronizerSessionManager
    --SessionManager.database_filepath=jupyter-database.db \
    --SynchronizerSessionManager.autosync=True \
    --SynchronizerSessionManager.log_level=DEBUG
```
