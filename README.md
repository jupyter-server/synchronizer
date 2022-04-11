# Jupyter Server Synchronizer

A server extension that synchronizes all managers in a running Jupyter Server.

This is particularly useful for Jupyter Servers running remote kernels and contents.

## Basic usage

Install and enable the extension:

```
pip install jupyter_server_synchronizer

jupyter server extension enable jupyter_server_synchronizer
```

When you start a Jupyter Server, it synchronize all managers before the Web application is started.

```
jupyter server
```

To synchronize periodically, enable the auto-synchronizing feature using the `autosync` config option. For example,

```
jupyter server --SynchronizerExtension.autosync=True
```

Otherwise, you can trigger the synchronization making a `POST` request to the `/api/sync` endpoint.
