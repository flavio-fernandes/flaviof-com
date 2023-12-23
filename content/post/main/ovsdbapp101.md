+++
author = "flaviof"
categories = ["main"]
date = "2019-11-30T17:01:00-05:00"
tags = ["bash", "ovn", "python"]
title = "OVN via OVSDBApp"
series = "Hacking OVN"
+++

Configuring OVN natively using a python library

<!--more-->

I recently came across a [nice bash script][script] written by [Russell][] that creates
logical switches, a logical router, and ACLs in [OVN][]. It also tests
that config using bound OVS ports from namespaces.
In the real world, a CMS (like Openstack) uses a python library, called *ovsdbapp*, to
establish a session and talk natively with the OVN database. I rewrote part
of Russell's script to give you an idea of how that gets done. So, if you find yourself
using the *ovn-nbctl* and *ovn-sbctl* commands a lot, read on to learn more about a nice
way of working with OVN.

Parallel to that, I also wanted to see how fast I could get a VM
running OVN from scratch. I was happy to see that this can be accomplished
in a little over 1 minute! For that, I leveraged Vagrant with the [centos 8 box][c8]
and the [packages built in RDO][rdo]. If you need more info on having Vagrant with
libvirt, take a look at [this other blog][vglibv] that I wrote.

To get started, [install Vagrant][vginstall] and bring up the VM using the following repo:

```
$ git clone -b blog \
  https://github.com/flavio-fernandes/ovsdbapp_playground.git && \
  cd ovsdbapp_playground && \
  time vagrant up
```

Looking at the [Vagrantfile][repo], you can see how the VM provisioning adds RDO as the repository
where the OVS+OVN packages are located.
Once up, ssh into the VM and run [this script][steps.sh] to quickly ensure that the provisioning
went well:

```
$ vagrant ssh

(.env) [vagrant@localhost ~]$ ./scripts/steps.sh
```

It all happens quickly, but here are the main pieces that get exercised
via *[steps.sh][]*:

1. create OVS ports inside namespaces
1. configure OVN with logical switches, ports, router and ACLs
1. test the connectivity based on ACLs and ports bound at namespace
1. undo config and creation of namespaces

Note that each step is actually a separate file that you can explicitly run.
Use that to take yourself to the point that interests you and poke around.

There are lots of interesting things to cover here, but I'm focusing on what
happens in step 2 above. That is where *[ovsdbapp][]* comes into the
picture. Using that, native [OVSDB RPCs][ovsdbrfc] populate OVN's
northbound tables.
*ovsdbapp* is [installed via pip][ovsdbapppip] during the provisioning. That
is a self-contained library that can be cloned via Github (or Gerrit):

<center>https://github.com/openstack/ovsdbapp</center>
<center>https://review.opendev.org/#/q/project:openstack/ovsdbapp</center>

While *ovsdbapp* is generic enough to be used with any OVSDB schema,
[many helpers][ovsdbappnbapi] exist to make life easy in dealing with
the [OVN Northbound DB][ovnnbschema]. There is also an API for
[OVN Southbound][ovsdbappsbapi] and [open_vswitch][ovsdbappovsapi].

```
$ pip install ovsdbapp
```

Once *ovsdbapp* is installed, the first thing we need to do is to connect it
to the right OVSDB server. In this case, that is the OVN Northbound. These
servers can be configured to connect in several ways, including SSL, TCP or
Unix sockets. With the command below, we can make it listen on TCP port
6641 on the loopback address:

```
$ sudo ovn-nbctl set-connection ptcp:6641:127.0.0.1
```

Let's jump into interactive python and connect to
OVN's NB:

Python
```
from ovsdbapp.backend.ovs_idl import connection
from ovsdbapp.schema.ovn_northbound import impl_idl

conn = "tcp:127.0.0.1:6641"

# The python-ovs Idl class. Take it from server's database
i = connection.OvsdbIdl.from_server(conn, 'OVN_Northbound')

# The ovsdbapp Connection object
c = connection.Connection(idl=i, timeout=3)

# The OVN_Northbound API implementation object
api = impl_idl.OvnNbApiIdlImpl(c)
```

At this point, we have a working API to a running OVN Norhbound database! Let's create
the most common component OVN uses (a logical switch):

```
api.ls_add("sw0").execute()
```

With OVSDB, many changes can be grouped into a single transaction. To give you
an idea of how that can be accomplished using *ovsdbapp*, take a look at this example:

```
# Create a transaction and add a logical switch with 2 ports
with api.transaction(check_error=True) as txn:
    txn.add(api.ls_add("sw1"))
    txn.add(api.lsp_add("sw1", "sw1-port1"))
    txn.add(api.lsp_set_addresses("sw1-port1", ["50:54:00:00:00:01 11.0.0.1"]))
    txn.add(api.lsp_add("sw1", "sw1-port2"))
    txn.add(api.lsp_set_addresses("sw1-port2", ["50:54:00:00:00:02 11.0.0.2"]))
```

Tables can be iterated with some simple commands. For instance:

```
for ls_row in api.ls_list().execute(check_error=True):
    print("uuid: %s, name: %s" % (ls_row.uuid, ls_row.name))
    for lsp_row in api.lsp_list(switch=ls_row.uuid).execute():
        print("  uuid: %s, name: %s" % (lsp_row.uuid, lsp_row.name))
```

Look at [lines 59 to 75 of step2 script][step2_create_logical_ports.py] to see a transaction
that creates a virtual logical router and its ports. That file also creates ACLs, which is an OVN
feature flexible enough to handle all that Openstack [security groups][sgs] need and more.

Lastly, here is a recording that shows an interactive python session using *ovsdbapp*.
It uses the commands mentioned above, so you can have an idea of what these
return:
[![asciicast](https://asciinema.org/a/284594.svg)](https://asciinema.org/a/284594?t=21)

All in all, I hope that this page helps as an intro on *ovsdbapp* and how it can be used for
handling OVN. There are tons more that this module can do and that is not related
to OVN. So do not stop here! Many thanks to [Terry Wilson][Terry] for writing this neat library
and help me learn it.

Also see:

- [Networking-OVN](https://github.com/openstack/networking-ovn): A heavy user of ovsdbapp
- [Neutron OVN client idl](https://medoc.readthedocs.io/en/latest/docs/ovs/ovn/idl/3_ovn_client_idl.html#)
- [OpenStack Security Groups using OVN ACLs](https://blog.russellbryant.net/2015/10/22/openstack-security-groups-using-ovn-acls/)

[script]: https://gist.github.com/russellb/4ab0a9641f12f8ac66fdd6822ee7789e "Bash script that configures and tests OVN"
[OVN]: https://github.com/ovn-org/ovn/blob/9f7f466af94cb45c03bac08abab87602272f3058/README.rst "Open Virtual Network"
[Russell]: https://github.com/russellb "Russell Bryant"
[c8]: https://app.vagrantup.com/centos "Vagrant Centos 8 Box"
[rdo]: https://trunk.rdoproject.org/ "RDO Trunk Development"
[vginstall]: https://www.vagrantup.com/downloads.html "Get Vagrant"
[vglibv]: https://www.flaviof.com/blog2/post/hacks/vagrant-libvirt/ "Installing Vagrant libvirt"
[repo]: https://github.com/flavio-fernandes/ovsdbapp_playground/blob/396ffc8b76ca560f014502dc864994264cef0c9c/Vagrantfile#L11-L19 "RDO Repo that has OVS and OVN"
[steps.sh]: https://github.com/flavio-fernandes/ovsdbapp_playground/blob/blog/scripts/steps.sh "steps.sh -- config, test and unconfig OVN setup"
[ovsdbapp]: https://github.com/openstack/ovsdbapp "OVSDB App"
[ovsdbrfc]: https://tools.ietf.org/html/rfc7047 "The Open vSwitch Database Management Protocol"
[ovsdbapppip]: https://github.com/flavio-fernandes/ovsdbapp_playground/blob/396ffc8b76ca560f014502dc864994264cef0c9c/Vagrantfile#L43 "pip install ovsdbapp"
[ovsdbappnbapi]: https://github.com/openstack/ovsdbapp/blob/0bd24c269d07e1181d9e6a7ed4267a63d7ad1921/ovsdbapp/schema/ovn_northbound/api.py#L22 "OVN NB helpers in OVSDB App"
[ovsdbappsbapi]: https://github.com/openstack/ovsdbapp/blob/0bd24c269d07e1181d9e6a7ed4267a63d7ad1921/ovsdbapp/schema/ovn_southbound/api.py "OVN SB helpers in OVSDB App"
[ovsdbappovsapi]: https://github.com/openstack/ovsdbapp/blob/0bd24c269d07e1181d9e6a7ed4267a63d7ad1921/ovsdbapp/schema/open_vswitch/api.py "OVS helpers in OVSDB App"
[ovnnbschema]: https://github.com/ovn-org/ovn/blob/master/ovn-nb.ovsschema "OVN Northbound schema"
[step2_create_logical_ports.py]: https://github.com/flavio-fernandes/ovsdbapp_playground/blob/396ffc8b76ca560f014502dc864994264cef0c9c/scripts/step2_create_logical_ports.py#L59-L75 "Creating virtual logical router"
[sgs]: https://wiki.openstack.org/wiki/Neutron/SecurityGroups "Openstack Neutron Security Groups"
[Terry]: https://github.com/otherwiseguy "otherwiseguy"
