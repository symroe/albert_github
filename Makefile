python_plugin_dir = ~/.local/share/albert/python/plugins/gh/

plugin_dir:
	mkdir -p $(python_plugin_dir)

install: plugin_dir
	cp *.py $(python_plugin_dir)
	albert restart
