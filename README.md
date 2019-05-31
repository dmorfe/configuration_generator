# configuration_generator
Excel, Jinja2 and Yaml generator

The config_gen_excel.py will read an excel Subnet planner and an excel Port Matrix workbooks and will generate device(s) config files base on Jinja2 template. It will also convert the devices dictionary into YAML and save it into a file and it will also generate an Ansible YAML playbook so if changes need to be done for a device, user just has to make changes to the device YAML config file and then run the device Ansible playbook.

The generated files will be save under the host name pulled from the Excel workbook.

## DO NOT ALTER THE SPREADSHEET NAMES(COLUMNS and TABs) AND DO NOT ALTER THE COLUMNS POSITIONS. IF YOU DO THE PROGRAM WILL BREAK.

# File description:
  - L2 Template.j2 - Sample Jinja2 template to use to generate device config(s).
  - PortMatrix.xlsx - Sample Port Matrix Excel spreadsheet template to be use to map the ports from AL(s) to DL(s).
  - SubnetPlanning.xlsx - Sample Subnet Planning Excel spreadsheet to use as a template when creating the subnet plan.
  - ansible-playbook.j2 - Jinja2 template used to generate device Ansible playbook to be used in case a device(s) need some changes in
                          their configuration and the engineer doesn't want to run the Python program to generate all device
                          configurations.
                          To recreate a device config from the Yaml configuration file you need the following files:
                            - {device name}.yaml
                            - {device jinja2 template}.j2
                            - {device name-Ansible-playbook}.yaml
                           Once you have all 3 files under the same directory structure, run the following command:
                            - ansible-playbook {device name-Ansible-playbook}.yaml
                            
     
  - config_gen_excel.py
