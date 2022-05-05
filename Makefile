.PHONY: kg lab kill

kg:
	jupyter kernelgateway \
		--port 9999 \
		--JupyterWebsocketPersonality.list_kernels=True

lab:
	jupyter lab \
		--gateway-url=http://127.0.0.1:9999 \
		--ServerApp.session_manager_class='jupyter_server_synchronizer.SynchronizerSessionManager' \
		--SynchronizerSessionManager.database_filepath=jupyter-database.db \
		--ServerApp.log_level=DEBUG

teardown:
	kill -9 $$(echo $$(pgrep -lf jupyter-lab) | awk '{print $$1;}')
