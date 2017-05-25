#!/usr/bin/env python

import boto.ec2
import boto.ec2.autoscale
from boto.ec2.connection import EC2Connection
from boto.ec2.autoscale.launchconfig import LaunchConfiguration
from boto.ec2.autoscale.group import AutoScalingGroup
from boto.ec2.autoscale import Tag
import ConfigParser
import logging
from datetime import datetime
import os

###################################
# config sections
###################################
config_filename = "/var/lib/jenkins/workspace/AWS-Demo/cm/ec2-deploy.conf"

def get_autoscale_group(asg_name, conn):
    asgroups = conn.get_all_groups(names = [asg_name])
    # there should only be one
    if len(asgroups) == 1:
        return asgroups[0]
    return None

def sgnames_to_list(namestring, region):
    sgconn = boto.connect_ec2()
    sgnames = namestring.split(',')
    print sgnames
    # question if the boto aws connections are all the same, or whether i need to spool up
    # a separate connection for the non-autoscale ec2 stuff
    rgnsglist = sgconn.get_all_security_groups( )
    securityGroups = []
    
    for securityGroup in rgnsglist:
        found = False
        for sGroup in sgnames:
            if (securityGroup.name == sGroup):
                found = True
                securityGroups.append(securityGroup)
                break
    if len(securityGroups) > 0:
        return securityGroups
    return None


def main():

    # pseudocode (repeats in code comments below)
    # check for autoscale group
    # if autoscale group not present, create it
    # else read launchconfig name from asg
    # define new launchconfig
    # assign launchconfig
    # delete old launchconfig - we can only have so many



    # read config
    print "reading configuration ..."
    config = ConfigParser.SafeConfigParser(allow_no_value=True)
    # This assumes that the file is either in the local directory being ran, or in the home/aws/ folder
    # We have to use the second option because XLD does not run the script in the same location that it's located
    config.read(['ec2-deploy.conf', os.path.expanduser('/var/lib/jenkins/workspace/AWS-Demo/cm/ec2-deploy.conf')])
    # check for autoscale group
    # FIXME: Should connect to region there
    # FIXME: proxy information?
    print "connecting to ec2..."
    #asconn = boto.ec2.autoscale.AutoScaleConnection(aws_access_key_id=config.get('auth', 'AWS_ACCESS_KEY_ID'), 
        #aws_secret_access_key=config.get('auth', 'AWS_SECRET_ACCESS_KEY'), security_token=config.get('auth', 'AWS_SECURITY_TOKEN'))
    #boto.set_stream_logger('boto')
    asconn = boto.ec2.autoscale.AutoScaleConnection()

    print "validating autoscaling group ..."
    asg = get_autoscale_group(config.get('autoscalegroup','name'), asconn)
    oldlc = None
    # read userdata
    userdata = ""
    with open(config.get('launchconfig', 'userdata_filename'), 'r') as udf:
        userdata=udf.read() 
    
    # define new launchconfig

    timenow = str(datetime.now()).split(".")[0]
    timenow = timenow.replace(" ", "").replace("-", "").replace(":", "")

    lcname = config.get('autoscalegroup', 'name') + "-lc-" + timenow
    print "Creating new launch config '{}'".format(lcname)
    newlc = LaunchConfiguration(
        name = lcname,
        image_id = config.get('launchconfig', 'ami'),
        key_name = config.get('launchconfig', 'keypair'),
        instance_type = config.get('launchconfig', 'instancetype'),
        # security_groups = sgnames_to_list( config.get('launchconfig', 'sgnames') , config.get('ec2', 'region')),
        security_groups = str(config.get('launchconfig', 'security_groups')).split(','),
        # classic_link_vpc_security_groups = str(config.get('launchconfig', 'security_groups')).split(','),         
        user_data = userdata,
        associate_public_ip_address = True,
        delete_on_termination = True,
        instance_monitoring = False,
        instance_profile_name = config.get('launchconfig', 'instance_profile_name')
        )
    print "new lc created"
    asconn.create_launch_configuration(newlc)
    print "lc associated, now checking if asg exists"
    # if autoscale group not present, create it
    if asg is None:
        print "Autoscaling Group '{}' not found, creating...".format(config.get('autoscalegroup', 'name'))
        azlist = str(config.get('autoscalegroup', 'azs')).split(',')
        elblist = str(config.get('autoscalegroup', 'elbs')).split(',')
        vpclist = str(config.get('launchconfig', 'subnet')).split(',')
        asg = AutoScalingGroup(
            connection = asconn,
            name = config.get('autoscalegroup', 'name'),
            load_balancers = elblist,
            availability_zones = azlist,
            desired_capacity = config.getint('autoscalegroup','desired_capacity'),
            launch_config = newlc,
            max_size = config.getint('autoscalegroup','max_size'),
            min_size = config.getint('autoscalegroup','min_size'),
            vpc_zone_identifier = vpclist
            )
        asconn.create_auto_scaling_group(asg)
        
    else:
        # else read launchconfig name from asg
        # Note that the oldlc is just the name of the lc we're about to delete
        oldlc = asg.launch_config_name
        print "Replacing launch configuration '{}' with new lc '{}'.".format(oldlc, lcname)
        asg.endElement("LaunchConfigurationName", lcname, asconn)
        asg.update()
        # this part now terminates each instance individually
        autoscale = boto.connect_autoscale()
        ec2 = boto.connect_ec2()
        group = autoscale.get_all_groups([config.get('autoscalegroup', 'name')])[0]
        instance_ids = [i.instance_id for i in group.instances]
        # reservations = ec2.get_all_instances(instance_ids)
        # instances = [i for r in reservations for i in r.instances]
        for i in instance_ids:
            asconn.terminate_instance(i,decrement_capacity=False)

    
    # delete old launchconfig - we can only have so many

    if oldlc is not None:
        print "Deleting old launch configuration ... "
        asconn.delete_launch_configuration(oldlc)
        print "done."
    
    # end main
    print "Now injecting the Name Tag"
    # can't figure out a better way to inject the boto Tag tag class - will need to fix later to make it look better
    taglist = Tag(key='Name', value=config.get('tags', 'name'), propagate_at_launch=True, resource_id=config.get('autoscalegroup', 'name'))
    asconn.create_or_update_tags([taglist])
# main stub
if __name__ == "__main__":
    main()
# end of file

