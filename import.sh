#!/bin/bash

# Usage:
#
#     poetry run ./import.sh username password
#
# Where 'username' and 'password' are your username and password for the
# Traveline National Dataset FTP server


# create lockfile
# I think it's important that this goes before the `trap`
mkdir /var/lock/bustimes-import || {
    echo "An import appears to be running already"
    exit 1
}

function finish {
    # remove lockfile
    rmdir /var/lock/bustimes-import 2> /dev/null
}
trap finish EXIT SIGINT SIGTERM

USERNAME=$1
PASSWORD=$2


./manage.py nptg_new
./manage.py naptan_new


cd data/TNDS

ncsd_old=$(ls -l NCSD.zip)
wget -qN http://www.basemap.co.uk/data/NCSD/NCSD.zip
ncsd_new=$(ls -l NCSD.zip)

cd ../..

if [[ $ncsd_old != $ncsd_new ]]; then
    ./manage.py import_transxchange data/TNDS/NCSD.zip
fi


./manage.py import_noc


if [[ $USERNAME == '' || $PASSWORD == '' ]]; then
   echo 'TNDS username and/or password not supplied :('
   exit 1
fi

./manage.py import_tnds "$USERNAME" "$PASSWORD"

./manage.py import_gtfs

finish
