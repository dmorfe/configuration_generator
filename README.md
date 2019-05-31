# configuration_generator
Excel, Jinja2 and Yaml generator

The config_gen_excel.py will read an excel workbook and will generate device(s) config files base on Jinja2 template. It will also convert the config parameters into YAML and save it into a file and generates an Ansible YAML playbook so if changes need to be done for a device user just has to make changes to the device YAML config file and then run the device Ansible playbook.

The generated files will be save under the host name pulled from the Excel workbook.

## DO NOT ALTER THE SPREADSHEET NAMES(COLUMNS and TABs) AND DO NOT ALTER THE COLUMNS POSITIONS. IF YOU DO THE PROGRAM WILL BREAK.
