#!/usr/bin/env python
# -*- coding: utf-8 -*-

##
# Copyright 2015 Telefónica Investigación y Desarrollo, S.A.U.
# This file is part of openmano
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact with: nfvlabs@tid.es
##

'''
This is the main program of openvim, it reads the configuration 
and launches the rest of threads: http clients, openflow controller
and host controllers  
'''

__author__="Alfonso Tierno"
__date__ ="$10-jul-2014 12:07:15$"
__version__="0.1.90-r355"
version_date="Mar 2015"

import httpserver
from utils import auxiliary_functions as af
import sys
import getopt
import time
import vim_db
import yaml
import os
from jsonschema import validate as js_v, exceptions as js_e
import host_thread as ht
import openflow_thread as oft
import threading
from vim_schema import config_schema

global config_dic

def load_configuration(configuration_file):
    default_tokens ={'http_port':9080, 'http_host':'localhost', 
                     'of_controller_nets_with_same_vlan':True,
                     'image_path':'/opt/VNF/images'
            }
    try:
        #First load configuration from configuration file
        #Check config file exists
        if not os.path.isfile(configuration_file):
            return (False, 'Error: Configuration file '+configuration_file+' does not exists.')
            
        #Read and parse file
        (return_status, code) = af.read_file(configuration_file)
        if not return_status:
            return (return_status, "Error loading configuration file '"+configuration_file+"': "+code)
        try:
            config = yaml.load(code)
        except yaml.YAMLError, exc:
            error_pos = ""
            if hasattr(exc, 'problem_mark'):
                mark = exc.problem_mark
                error_pos = " at position: (%s:%s)" % (mark.line+1, mark.column+1)
            return (False, "Error loading configuration file '"+configuration_file+"'"+error_pos+": content format error: Failed to parse yaml format")
        
        
        try:
            js_v(config, config_schema)
        except js_e.ValidationError, exc:
            error_pos = ""
            if len(exc.path)>0: error_pos=" at '" + ":".join(map(str, exc.path))+"'"
            return False, "Error loading configuration file '"+configuration_file+"'"+error_pos+": "+exc.message 
        
        
        #Check default values tokens
        for k,v in default_tokens.items():
            if k not in config: config[k]=v
    
    except Exception,e:
        return (False, "Error loading configuration file '"+configuration_file+"': "+str(e))
    return (True, config)

def create_database_connection(config_dic):
    db = vim_db.vim_db();
    if db.connect(config_dic['db_host'], config_dic['db_user'], config_dic['db_passwd'], config_dic['db_name']) == -1:
        print "Error connecting to database", config_dic['db_name'], "at", config_dic['db_user'], "@", config_dic['db_host']
        exit(-1)
    return db

def usage():
    print "Usage: ", sys.argv[0], "[options]"
    print "      -v|--version: prints current version"
    print "      -c|--config [configuration_file]: loads the configuration file (default: openvimd.cfg)"
    print "      -h|--help: shows this help"
    print "      -p|--port [port_number]: changes port number and overrides the port number in the configuration file (default: 9090)"
    print "      -P|--adminport [port_number]: changes admin port number and overrides the port number in the configuration file (default: 9095)"
    return


if __name__=="__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvc:p:P:", ["config", "help", "version", "port", "adminport"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print "Error:", err # will print something like "option -a not recognized"
        usage()
        sys.exit(-2)

    port=None
    port_admin = None
    config_file = 'openvimd.cfg'

    for o, a in opts:
        if o in ("-v", "--version"):
            print "openvimd version", __version__, version_date
            print "(c) Copyright Telefonica"
            sys.exit(0)
        elif o in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif o in ("-c", "--config"):
            config_file = a
        elif o in ("-p", "--port"):
            port = a
        elif o in ("-P", "--adminport"):
            port_admin = a
        else:
            assert False, "Unhandled option"

    
    try:
        #Load configuration file
        r, config_dic = load_configuration(config_file)
        #print config_dic
        if not r:
            print config_dic
            config_dic={}
            exit(-1)
        #override parameters obtained by command line
        if port is not None: config_dic['http_port'] = port
        if port_admin is not None: config_dic['http_admin_port'] = port_admin
        
        #check mode
        if 'mode' not in config_dic:
            config_dic['mode'] = 'normal'
            #allow backward compatibility of test_mode option
            if 'test_mode' in config_dic and config_dic['test_mode']==True:
                config_dic['mode'] = 'test' 
            
        if config_dic['mode'] != 'normal':
            print '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
            print "!! Warning, openvimd in TEST mode '%s'" % config_dic['mode']
            print '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
        config_dic['version'] = __version__

    #Connect to database
        db_http = create_database_connection(config_dic)
        db_of = create_database_connection(config_dic)
        db_lock= threading.Lock()
        config_dic['db'] = db_of
        config_dic['db_lock'] = db_lock

    #create openflow thread
        of_test_mode = False if config_dic['mode']=='normal' else True
        thread = oft.openflow_thread(of_url = "http://"+str(config_dic['of_controller_ip']) + ":"+ str(config_dic['of_controller_port']),
                        of_test=of_test_mode,
                        of_dpid=config_dic['of_controller_dpid'],
                        db=db_of,  db_lock=db_lock,
                        pmp_with_same_vlan=config_dic['of_controller_nets_with_same_vlan'])
        r,c = thread.get_of_controller_info()
        if r<c:
            print "Error getting openflow information", c
            exit()
        thread.start()
        config_dic['of_thread'] = thread
        
    #precreate interfaces; [bridge:<host_bridge_name>, VLAN used at Host, uuid of network camping in this bridge, speed in Gbit/s
        config_dic['bridge_nets']=[]
        for bridge,vlan_speed in config_dic["bridge_ifaces"].items():
            config_dic['bridge_nets'].append( [bridge, vlan_speed[0], vlan_speed[1], None] )
        del config_dic["bridge_ifaces"]

        #check if already present
        used_bridge_nets=[]
        for brnet in config_dic['bridge_nets']:
            r,c = db_of.get_table(SELECT=('uuid',), FROM='nets',WHERE={'bind': "bridge:"+brnet[0]})
            if r>0:
                brnet[3] = c[0]['uuid']
                used_bridge_nets.append(brnet[0])
        if len(used_bridge_nets) > 0 :
            print "found used bridge nets: " + ",".join(used_bridge_nets)
    
        
    #Create one thread for each host
        host_test_mode = True if config_dic['mode']=='test' else False
        config_dic['host_threads'] = {}
        r,c = db_of.get_table(SELECT=('name','ip_name','user','uuid'), FROM='hosts', WHERE={'status':'ok'})
        if r<0:
            print "Error getting hosts from database", c
            exit(-1)
        else:
            for host in c:
                host['image_path'] = '/opt/VNF/images/openvim'
                thread = ht.host_thread(name=host['name'], user=host['user'], host=host['ip_name'], db=db_of, db_lock=db_lock,
                        test=host_test_mode, image_path=config_dic['image_path'], version=config_dic['version'],
                        host_id=host['uuid']  )
                thread.start()
                config_dic['host_threads'][ host['uuid'] ] = thread
                
            
        
    #Create thread to listen to web requests
        http_thread = httpserver.httpserver(db_http, 'http', config_dic['http_host'], config_dic['http_port'], False, config_dic)
        http_thread.start()
        
        if 'http_admin_port' in config_dic: 
            db_http = create_database_connection(config_dic)
            http_thread_admin = httpserver.httpserver(db_http, 'http-admin', config_dic['http_host'], config_dic['http_admin_port'], True)
            http_thread_admin.start()
        else:
            http_thread_admin = None
        time.sleep(1)      
        print 'Waiting for http clients'
        print '===================='
        
        #TODO: Interactive console would be nice here instead of join or sleep
        
        r="help" #force print help at the beginning
        while True:
            if r=='exit':
                break      
            elif r!='':
                print "type 'exit' for terminate"
            r = raw_input('> ')

    except (KeyboardInterrupt, SystemExit):
        pass

    print 'Exiting openvimd'
    threads = config_dic.get('host_threads', {})
    if 'of_thread' in config_dic:
        threads['of'] = (config_dic['of_thread'])
    
    for thread in threads.values():
        thread.insert_task("exit")
    for thread in threads.values():
        thread.join()
    #http_thread.join()
    #if http_thread_admin is not None: 
    #http_thread_admin.join()
    print "bye!"
    exit()

