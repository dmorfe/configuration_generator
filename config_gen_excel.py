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
    parser.add_argument('--subplan',required=True, help='Subnet Planning name is required.')
    parser.add_argument('--portmatrix',required=True, help='Port Matrix name is required.')
    parser.add_argument('--configtype',required=True, help='Config type name is required. (AL/WL/SE')
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

# generate VLAN name
def GenVlanName(vlantype, swname):
    newVlanName = swname.replace('-','_')
    newVlanName = newVlanName.replace('IDF','0')
    newVlanName = newVlanName.replace('SE','0')
    newVlanName = newVlanName.replace('WL','0')
    newVlanName = newVlanName.replace('AL','0')

    return(vlantype + newVlanName)


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
        #print(threading.current_thread().name + '-' + dev_data['hostname'] + ' Submitted')
        GenerateConfig(dev_data)
        device_queue.task_done()
        #print(threading.current_thread().name + '-' + dev_data['hostname'] + ' Completed!!')

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
def ReadWorkBookIntoQueue(inputSubPlan, portMatrix):
    next_service = False
    worksheets = {}
    ManagementIP = ''
    ManagementMask = ''
    ManagementVLAN = ''
    dataSubnet = ''
    Subnetmask = 0
    current_floor = 0
    current_IDF_ID = ''
    current_service = ''
    mgmtIPoctect = 11

    portmatrixwb = excel.ExcelFile(portMatrix)

    if arguments.configtype.upper() == 'AL':
        configt = 'Data'
    elif arguments.configtype.upper() == 'WL':
        configt = 'Wireless'
    else:
        configt = 'Security Cameras'

    with excel.ExcelFile(inputSubPlan) as wb:
        for sname in wb.sheet_names:
            print('**** Sheet Name: '+ str(sname))
            #readsheet = excel.read_excel(wb,sheet_name=sname,converters={'Username':str,'Password':str,'Secret':str,'data_type':str,'Show_Commands':str,'Config_Commands':str})
            readsheet = excel.read_excel(wb,sheet_name=sname)
            df = DataFrame(data=readsheet, copy=True)
            worksheets[sname] = df.to_dict(orient='records')

            print('Finding management subnet and VLAN: \n')
            for rw in worksheets[sname]:
                if rw.get('Service') == 'Wired Switch Management' and configt == 'Data':
                    ManagementIP, ManagementMask = str(rw.get('Assigned Subnets')).split('/')
                    ManagementVLAN = rw.get('VLAN')
                    break
                elif rw.get('Service') == 'Wireless Switch Management' and configt == 'Wireless':
                    ManagementIP, ManagementMask = str(rw.get('Assigned Subnets')).split('/')
                    ManagementVLAN = rw.get('VLAN')
                    break
                else:
                    if rw.get('Service') == 'Security Switch Management'  and configt == 'Security Cameras':
                        ManagementIP, ManagementMask = str(rw.get('Assigned Subnets')).split('/')
                        ManagementVLAN = rw.get('VLAN')
                        break

            for rw in worksheets[sname]:
                if next_service and rw.get('Service') == rw.get('Service'):
                    break

                if rw.get('Service') == configt:
                    current_service = str(rw.get('Service')).strip()
                    print('found service: ', rw.get('Service'))

                if (current_service == configt):
                    print('processing next...')
                    switch_dict = {'hostname': '', 'IDFID': '', 'managementMask': '', 'ManagementIP': '', \
                    'datavlanname': '', 'datavlans': [], 'datasubnet': '', 'datamask': '', 'voicevlanname': '', \
                    'voicevlans': [], 'voicesubnet': '', 'voicemask': '',  'managementVLAN': '', 'managmentsubnet': '', \
                    'po': {'ponum': '', 'interfaces': {}}}

                    next_service = True
                    if rw.get('Floor') == rw.get('Floor'):
                        current_floor = rw.get('Floor')
                    if rw.get('IDF ID') == rw.get('IDF ID'):
                        current_IDF_ID = GenVlanName("",str(rw.get('Switch')).upper())

                    if rw.get('Assigned Subnets') == rw.get('Assigned Subnets'):
                        dataSubnet, Subnetmask = str(rw.get('Assigned Subnets')).split('/')

                    switch_dict['hostname'] = str(rw.get('Switch')).upper()
                    switch_dict['IDFID'] = current_IDF_ID
                    switch_dict['datasubnet'] = dataSubnet.strip()
                    switch_dict['datamask'] = cidr_to_netmask(Subnetmask)

                    if configt == 'Data' or configt == 'Wireless':
                        switch_dict['datavlanname'] = GenVlanName(configt + '_',switch_dict['hostname'])
                    else:
                        temp_service, garbage = configt.split(" ")
                        switch_dict['datavlanname'] = GenVlanName(temp_service + '_',switch_dict['hostname'])

                    switch_dict['managmentsubnet'], garbage = str(ManagementIP).strip().split('.0',3)

                    switch_dict['managementMask'] = cidr_to_netmask(ManagementMask)
                    switch_dict['managementVLAN'] = str(ManagementVLAN).strip()

                    if current_service == 'Data':
                        portmatrixsh = portmatrixwb.parse(sheet_name='6807 Wired VSS')
                        print('Processing AL Port Matrix ...')
                    elif current_service == 'Security Cameras':
                        portmatrixsh = portmatrixwb.parse(sheet_name='6840 SEC VSS')
                        print('Processing SE Port Matrix ...')
                    else:
                        portmatrixsh = portmatrixwb.parse(sheet_name='6807 WL VSS')
                        print('Processing WL Port Matrix ...')

                    for pmxrow in portmatrixsh.to_records():
                        # apply this logic to AL tab in port matrix
                        if str(switch_dict['hostname']).upper().strip() == str(pmxrow[7]).upper().strip():
                            switch_dict['po']['ponum'] = pmxrow[5][2:].strip()
                            switch_dict['po']['interfaces'][pmxrow[8]] = pmxrow[1]
                            switch_dict['po']['interfaces'][pmxrow[19]] = pmxrow[13]
                        # apply this logic to fields on WL and SEC in port matrix
                        if str(switch_dict['hostname']).upper().strip() == str(pmxrow[6]).upper().strip():
                            switch_dict['po']['ponum'] = pmxrow[4][2:].strip()
                            switch_dict['po']['interfaces'][pmxrow[7]] = pmxrow[1]
                            switch_dict['po']['interfaces'][pmxrow[16]] = pmxrow[11]

                    vl = str(rw.get('VLAN')).split('\n')
                    for vlan in vl:
                        vlantoadd = str(vlan)
                        switch_dict['datavlans'].append(vlantoadd)

                    if configt == 'Data':
                        switch_dict['ManagementIP'] = switch_dict['managmentsubnet'] + '.' + \
                        switch_dict['datavlans'][0][len(switch_dict['datavlans'])-3:]
                    else:
                        switch_dict['ManagementIP'] = switch_dict['managmentsubnet'] + '.' + str(mgmtIPoctect)
                        mgmtIPoctect = mgmtIPoctect + 3

                    # find voice vlan and add to dictionary
                    for vc in worksheets[sname]:
                        if vc.get('Service') == vc.get('Service'):
                            current_service_vc = vc.get('Service')

                        if current_service_vc == 'Voice' and str(vc.get('Switch')).upper() == str(switch_dict['hostname']).upper():
                            voiceSubnet, Subnetmask = str(vc.get('Assigned Subnets')).split('/')
                            switch_dict['voicevlanname'] = GenVlanName(current_service_vc + '_',switch_dict['hostname'])
                            switch_dict['voicesubnet'] = voiceSubnet.strip()
                            switch_dict['voicemask'] = cidr_to_netmask(Subnetmask)
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

    ReadWorkBookIntoQueue(arguments.subplan, arguments.portmatrix)

    device_queue.join()

    print(threading.enumerate())
    print('Generate Config completed successfully!!')

# call main function when program is ran
if __name__ == "__main__":
    main()
