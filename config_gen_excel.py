#!/usr/bin/env python
from pandas.io import excel
from pandas import DataFrame
from netmiko import ConnectHandler
from datetime import datetime
from getpass import getpass
import threading
from threading import Thread
from threading import Lock
from time import time
from queue import Queue
import argparse
import socket
import struct
from jinja2 import Environment, FileSystemLoader
import yaml

# default show commands
SHOWCOMMANDS = ['show run','show interface status','show vlan']

arguments = ''
templatefile = ''

TS_LIMIT = 20
QS_LIMIT = 50
TS_DEFAULT = 10
QS_DEFAULT = 20
WRITE_CONFIG_DEFAULT = 'N'

default_user = ''
default_pass = ''
default_secret = ''

device_queue = Queue()

# establishes connection to device and returns an object back
def connectToDevice(devcreds):
    ctd = ConnectHandler(**devcreds)
    return(ctd)

# create the header to be saved into log file for every command read from playbook
def get_logheader(commandSent):
    tmp = commandSent + " - " + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logHeader = "-" * len(tmp) + "\n" + tmp + "\n" + "-" * len(tmp) + "\n"
    return(logHeader)

# returns username. function will not exit unless something is entered.
def getusername():
    username = ''
    while username == '':
        username = input('Enter default username: ').strip()
    return(username)

# returns username. function will not exit unless something is entered. this function will not allow enty passwords but will allow for passwords with just spaces in it.
def getpassword(usern):
    password = ''
    while password == '':
        password = getpass('Enter ' + usern + ' password: ')
    return(password)

#parse arguments from command line
def getargs():
    parser = argparse.ArgumentParser(description='Playbook Runner by David Morfe')
    parser.add_argument('-i','--inputfile',required=True, help='inputfile name is required.')
    parser.add_argument('-t', '--j2template', required=True, help='Jinja2 Template file to use.')
    parser.add_argument('-w', help='specify if configuration should be save into Startup Config.\
     \'Y\' to write config \'N\' to preserve Startup Config. If this flag is not specified or any other \
     value is entered the default will be no to write the config changes.\nDefault: \'N\'')
    parser.add_argument('-ts', help='Number of Threads to be created.\nMust be a number from 1 thru 20\nIf a number \
    greater than 20 is entered, the maximum Thread number will be used.\nDefault: \'10\'')
    parser.add_argument('-qs', help='Queue size.\nMust be a number from 1 thru 50.\nIf a number greater than 50 is \
    entered, the maximum Queue number will used.\nDefault: \'20\'')
    parser.add_argument('-v','--version', action='version', version='%(prog)s 1.6')
    args = parser.parse_args()

    if args.w is None or (args.w.upper() != 'Y' and args.w.upper() != 'N'):
        args.w = WRITE_CONFIG_DEFAULT

    if args.qs is None:
        args.qs = QS_DEFAULT
    elif int(args.qs) > QS_LIMIT:
        args.qs = QS_LIMIT

    if args.ts is None:
        args.ts = TS_DEFAULT
    elif int(args.ts) > TS_LIMIT:
        args.ts = TS_LIMIT

    return(args)

# Initializes the threads. Expects an interger as a parameter.
def CreateThreads(n):
    print('Creating ' + str(n) + ' Threads')
    for x in range(int(n)):
        t = Thread(target=ThreadHandler)
        t.daemon = True
        t.start()

def ThreadHandler():
    while True:
        dev_data = device_queue.get()
        print(threading.current_thread().name + '-' + dev_data['hostname'] + ' Submitted')
        GenerateConfig(dev_data)
        device_queue.task_done()
        print(threading.current_thread().name + '-' + dev_data['hostname'] + ' Completed!!')

# open file to right log
def OpenOutputConfigFile(hostname):
    fileH = open(hostname + ".config",'w')
    return(fileH)

def WriteYamlFile(rw):
    fileH = open(rw.get('hostname') + ".yaml",'w')
    fileH.write(yaml.dump(rw, explicit_start=True, indent=5, default_flow_style=False))
    fileH.close()


# write command header and results to OpenOutputConfigFile
def WriteConfig(dicttowr, fileh):
    #Load Jinja2 template
    env = Environment(loader = FileSystemLoader('./'), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template(templatefile)

    #Render template using data and print the output
    GenarateDevConfig = template.render(dicttowr)
    print(GenarateDevConfig)
    fileh.write(GenarateDevConfig)

# Connects to device runs commands and creates and log file
def GenerateConfig(rw):
    fh = OpenOutputConfigFile(rw['hostname'])
    WriteConfig(rw, fh)
    WriteYamlFile(rw)
    fh.close()

def cidr_to_netmask(cidr):
    host_bits = 32 - int(cidr)
    netmask = socket.inet_ntoa(struct.pack('!I', (1 << 32) - (1 << host_bits)))
    return netmask

# open Excel Workbook and reaad rows and queue for processing
def ReadWorkBookIntoQueue(inputWB):
    worksheets = {}
    ManagementIP = ''
    ManagementMask = ''
    ManagementVLAN = ''
    current_floor = ''
    current_IDF_ID = ''
    current_service = ''

    with excel.ExcelFile(inputWB) as wb:
        for sname in wb.sheet_names:
            print('**** Sheet Name: '+ str(sname))
            #readsheet = excel.read_excel(wb,sheet_name=sname,converters={'Username':str,'Password':str,'Secret':str,'data_type':str,'Show_Commands':str,'Config_Commands':str})
            readsheet = excel.read_excel(wb,sheet_name=sname)
            df = DataFrame(data=readsheet, copy=True)
            worksheets[sname] = df.to_dict(orient='records')

            print('Finding management subnet and VLAN: \n')
            for rw in worksheets[sname]:
                print(rw.get('Service'))
                if rw.get('Service') == 'Wired Switch Management':
                    ManagementIP, ManagementMask = str(rw.get('Assigned Subnets')).split('/')
                    ManagementVLAN = rw.get('VLAN')
                    break

            for rw in worksheets[sname]:
                if rw.get('Service') == rw.get('Service'):
                    current_service = rw.get('Service')

                if current_service.strip() == 'Data' or current_service.strip() == 'Security Cameras' or current_service.strip() == 'Security Cameras':
                    switch_dict = {'hostname': '', 'IDFID': '', 'datavlanname': '', 'datavlans': [], 'datasubnet': '', 'datamask': '', 'voicevlanname': '', 'voicevlans': [], \
                    'voicesubnet': '', 'voicemask': '',  'managementVLAN': '', 'managmentsubnet': '', 'managementMask': '', 'ManagementIP': ''}

                    if rw.get('Floor') == rw.get('Floor'):
                        current_floor = rw.get('Floor')
                    if rw.get('IDF ID') == rw.get('IDF ID'):
                        current_IDF_ID = rw.get('IDF ID')

                    if rw.get('Assigned Subnets') == rw.get('Assigned Subnets'):
                        dataSubnet, Subnetmask = str(rw.get('Assigned Subnets')).split('/')

                    switch_dict['hostname'] = str(rw.get('Switch')).upper()
                    switch_dict['IDFID'] = current_IDF_ID
                    switch_dict['datasubnet'] = dataSubnet.strip()
                    switch_dict['datamask'] = cidr_to_netmask(Subnetmask)
                    switch_dict['datavlanname'] = current_service
                    switch_dict['managmentsubnet'], garbage = str(ManagementIP).strip().split('.0',3)
                    if rw.get('ManagementIP') == rw.get('ManagementIP'):
                        switch_dict['ManagementIP'], garbage = str(rw.get('ManagementIP')).split('.0')

                    switch_dict['managementMask'] = cidr_to_netmask(ManagementMask)
                    switch_dict['managementVLAN'] = str(ManagementVLAN).strip()

                    vl = str(rw.get('VLAN')).split('\n')
                    for vlan in vl:
                        vlantoadd = str(vlan)
                        switch_dict['datavlans'].append(vlantoadd)

                    # find voice vlan and add to dictionary
                    for vc in worksheets[sname]:
                        if vc.get('Service') == vc.get('Service'):
                            current_service_vc = vc.get('Service')

                        if current_service_vc == 'Voice' and str(vc.get('Switch')).upper() == str(switch_dict['hostname']).upper():
                            voiceSubnet, Subnetmask = str(vc.get('Assigned Subnets')).split('/')
                            switch_dict['voicevlanname'] = current_service_vc
                            switch_dict['voicesubnet'] = voiceSubnet.strip()
                            switch_dict['voicemask'] = cidr_to_netmask(Subnetmask)
                            print('voice vlan: ', vc.get('VLAN'))
                            vl = str(vc.get('VLAN')).split('\n')
                            for vlan in vl:
                                vlantoadd = str(vlan)
                                switch_dict['voicevlans'].append(vlantoadd)
                            break
                    print(switch_dict)
                    print('Generating Config ....> ')
                    GenerateConfig(switch_dict)
                    device_queue.put(switch_dict)

# program entry point
def main():
    global default_user
    global default_pass
    global default_secret
    global arguments
    global templatefile

    #read arn parse arguments from command line
    arguments = getargs()
    templatefile = arguments.j2template
    # device_queue.maxsize(arguments.qs)
    print('Setting max Queue size to: ', arguments.qs)
    device_queue.maxsize = int(arguments.qs)

    #default_user = getusername()
    #default_pass = getpassword(default_user)
    #default_secret = getpassword('enable/secret')

    # Initializes the threads.
    CreateThreads(arguments.ts)

    ReadWorkBookIntoQueue(arguments.inputfile)

    device_queue.join()

    print(threading.enumerate())
    print('Generate Config completed successfully!!')

# call main function when program is ran
if __name__ == "__main__":
    main()
