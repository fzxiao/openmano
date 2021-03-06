#!/bin/bash

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

#Get needed packets, source code and configure to run openvim, openmano and floodlight
#Ask for database user and password if not provided
#        $1: database user
#        $2: database password 

function usage(){
    echo  -e "usage: sudo $0 [db-user [db-passwd]]\n  Install source code in ./openmano"
    exit 1
}

#check root privileges and non a root user behind
[ "$USER" != "root" ] && echo "Needed root privileges" && usage
[ -z "$SUDO_USER" -o "$SUDO_USER" = "root" ] && echo "Must be runned with sudo from a non root user" && usage




echo '
#################################################################
#####        INSTALL LAMP   PACKETS                         #####
#################################################################'
apt-get update -y
apt-get install -y apache2 mysql-server php5 php-pear php5-mysql

#check and ask for database user password. Must be done after MYSQL instalation
[ -n "$1" ] && DBUSER=$1
[ -z "$1" ] && DBUSER=root
[ -n "$2" ] && DBPASSWD=$2
while [ -z "$DBPASSWD" ] || !  echo "" | mysql -u$DBUSER -p"$DBPASSWD" 
do
        [ -n "$logintry" ] &&  echo -e "\nInvalid database credentials!!!. Try again (Ctrl+c to abort)"
        [ -z "$logintry" ] &&  echo -e "\nProvide database credentials"
        read -p "mysql user($DBUSER): " DBUSER_
        [ -n "$DBUSER_" ] && DBUSER=$DBUSER_
        read -p "mysql password: " DBPASSWD
        logintry="yes"
done

echo '
#################################################################
#####        INSTALL PYTHON PACKETS                         #####
#################################################################'
apt-get update -y
apt-get install -y apache2 mysql-server php5 php-pear php5-mysql
apt-get install -y python-yaml python-libvirt python-bottle python-mysqldb python-jsonschema python-paramiko python-bs4 python-argcomplete git screen


echo '
#################################################################
#####        DOWNLOAD SOURCE                                #####
#################################################################'
su $SUDO_USER -c 'git clone https://github.com/nfvlabs/openmano.git openmano'

echo '
#################################################################
#####        CREATE DATABASE                                #####
#################################################################'
mysqladmin -u$DBUSER -p$DBPASSWD create vim_db
mysqladmin -u$DBUSER -p$DBPASSWD create mano_db

echo "CREATE USER 'vim'@'localhost' identified by 'vimpw';"     | mysql -u$DBUSER -p$DBPASSWD
echo "GRANT ALL PRIVILEGES ON vim_db.* TO 'vim'@'localhost';"   | mysql -u$DBUSER -p$DBPASSWD
echo "CREATE USER 'mano'@'localhost' identified by 'manopw';"   | mysql -u$DBUSER -p$DBPASSWD
echo "GRANT ALL PRIVILEGES ON mano_db.* TO 'mano'@'localhost';" | mysql -u$DBUSER -p$DBPASSWD

echo "vim database"
su $SUDO_USER -c './openmano/openvim/database_utils/init_vim_db.sh vim vimpw vim_db'
echo "mano database"
su $SUDO_USER -c './openmano/openmano/database_utils/init_mano_db.sh mano manopw mano_db'


echo '
#################################################################
#####        DOWNLOADING AND CONFIGURE FLOODLIGHT           #####
#################################################################'
#FLoodLight
echo "Installing FloodLight requires Java, that takes a while to download"
read -p "Do you agree on download and install FloodLight from http://www.projectfloodlight.org upon the owner license? (y/N)" KK
echo $KK
if [ "$KK" == "y" -o   "$KK" == "yes" ]
then

    echo "downloading v0.90 from the oficial page"
    su $SUDO_USER -c 'wget http://floodlight-download.projectfloodlight.org/files/floodlight-source-0.90.tar.gz'
    su $SUDO_USER -c 'tar xvzf floodlight-source-0.90.tar.gz'
    
    #Install Java JDK and Ant packages at the VM 
    apt-get install  -y build-essential default-jdk ant python-dev

    #Configure Java environment variables. It is seem that is not needed!!!
    #export JAVA_HOME=/usr/lib/jvm/default-java" >> /home/${SUDO_USER}/.bashr
    #export PATH=$PATH:$JAVA_HOME
    #echo "export JAVA_HOME=/usr/lib/jvm/default-java" >> /home/${SUDO_USER}/.bashrc
    #echo "export PATH=$PATH:$JAVA_HOME" >> /home/${SUDO_USER}/.bashrc

    #Compile floodlight
    pushd ./floodlight-0.90
    su $SUDO_USER -c 'ant'
    popd
    OPENFLOW_INSTALED="FloodLight, "
else
    echo "skipping!"
fi


echo '
#################################################################
#####        CONFIGURE OPENMANO-GUI WEB                     #####
#################################################################'
#allow apache user (www-data) grant access to the files, changing user owner
chown -R www-data ./openmano/openmano-gui
#create a link 
ln -s ${PWD}/openmano/openmano-gui /var/www/html/mano

echo '
#################################################################
#####        CONFIGURE openvim openmano CLIENTS             #####
#################################################################'
#creates a link at ~/bin
su $SUDO_USER -c 'mkdir -p ~/bin'
rm -f /home/${SUDO_USER}/bin/openvim
rm -f /home/${SUDO_USER}/bin/openmano
ln -s ${PWD}/openmano/openvim/openvim   /home/${SUDO_USER}/bin/openvim
ln -s ${PWD}/openmano/openmano/openmano /home/${SUDO_USER}/bin/openmano

#insert /home/<user>/bin in the PATH
#skiped because normally this is done authomatically when ~/bin exist
#if ! su $SUDO_USER -c 'echo $PATH' | grep -q "/home/${SUDO_USER}/bin"
#then
#    echo "    inserting /home/$SUDO_USER/bin in the PATH at .bashrc"
#    su $SUDO_USER -c 'echo "PATH=\$PATH:/home/\${USER}/bin" >> ~/.bashrc'
#fi

#configure arg-autocomplete for this user
su $SUDO_USER -c 'mkdir -p ~/.bash_completion.d'
su $SUDO_USER -c 'activate-global-python-argcomplete --dest=/home/${USER}/.bash_completion.d'
if ! grep -q bash_completion.d/python-argcomplete.sh /home/${SUDO_USER}/.bashrc
then
    echo "    inserting .bash_completion.d/python-argcomplete.sh execution at .bashrc"
    su $SUDO_USER -c 'echo ". .bash_completion.d/python-argcomplete.sh" >> ~/.bashrc'
fi

echo
echo "Done!  you may need to logout and login again for loading the configuration"
echo " Run './openmano/scripts/start-all.sh' for starting ${OPENFLOW_INSTALED}openvim and openmano in a screen"





