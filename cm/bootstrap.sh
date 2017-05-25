#!/bin/bash
yum install httpd -y
yum update -y
aws s3 cp s3://ledavin-builds/jobs/AWS-Demo/latest.txt ./latest.txt
aws s3 cp s3://ledavin-builds/jobs/AWS-Demo/`(cat latest.txt)`/artifacts/index.html /var/www/html/index.html
service httpd start
chkconfig httpd on
