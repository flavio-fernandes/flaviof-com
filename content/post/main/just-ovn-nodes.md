+++
author = "flaviof"
categories = ["main"]
date = "2016-07-28T01:39:42-04:00"
tags = ["ovn"]
title = "just ovn nodes"
series = "Hacking OVN"
+++

Deploy OVN in minutes in a setup that is independent of OpenStack.

<!--more-->

As it is normally the case, _Open Virtual Network_ (aka [OVN][]) is used in 
conjunction
with a _Cloud Management System_ (aka CMS). _OpenStack_ (aka [O/S][]) being the one that
[many][OSComm] companies use. The project
that connects these 2 pieces is [networking-ovn][], which is now implemented as a 
neutron [module layer 2][ml2] plugin.

I have played a bit with OpenStack in [past adventures][osPast] but have recently shifted my focus
to OVN. In order to get better at that, I find it best to do a bit of [divide and conquer][divAndC]
and initially leave the OpenStack portion out.

# OVN in a sandbox

A simple way of getting OVN up and running is by using
the sandbox, which is heavily used by the [unit test][ovsTest]. A great reference for using that
can be found in [OVN-Tutorial.md][].

If you are curious about another example on using the OVN within a sandbox, check out the
[output below][ovnSandbox]:

{{< gist anonymous 08f3d07aff4a26e368da3e5e12c7e3a1 >}}

However, using the sandbox has some limitations:

  - OVS' fake (aka dummy) datapath offers only a subset of the functionality that is available by kernel.
    [ACL and Conntrack][ovnAcl], to name a few.

  - Unable to use Linux [lxc][] to provide namespaces (isolated ip stack instances).
    Because OVS ports in a sandbox cannot be scoped by their own tcp/ip stack, it is not possible to
    use powerful tools like _ping_ to generate traffic and see the rules in action.
    Isolated ARP and routing tables are just not possible.
    You will have to resort to using commands like **ovs-appctl netdev-dummy/receive**,
    as shown at the end of the [sandbox][ovnSandbox] example above.

## Making the case for just-ovn-nodes

Thus, to have something more _realistic_ than the sandbox, but yet not as _complex_ as an
[OVN + networking-ovn + O/S deployment][networkingOvnVagrant], you can simply use
**[just-ovn-nodes][]**! Using [Vagrant][], this repo
gives us an automated way of getting all the pieces for a multi-node deployment with OVN. This
can be used as a throwaway setup ([cattle][petCattle]) used for quickly trying something out;
or as a starting place for creating a ([pet][petCattle]) cluster for OVN development.
Bear in mind I'm not the only one who has reached this serendipity. :) Folks like Guru --
undoubtfully one of my awesome gurus --
have a [similar repo][guruOvnNs] 
available. So, be sure to look around too.

### Pre-requisites

Here are the dependencies for using [just-ovn-nodes][]:

- Hypervisor (any that is supported by Vagrant)
- git
- Vagrant
- Vagrant plugins (see below)

#### Vagrant plugins

    for p in vagrant-reload sahara vagrant-cachier ; do \
       vagrant plugin install $p
    done

Vagrant plugin **vagrant-reload** is needed, so the provisioning of the node
VMS can reboot them after installing a newer kernel in the trusty box.
That is necessary, so OVN controllers can use the [Geneve][] encapsulation in
order to reach each other through an overlay network.

Vagrant plugin **sahara** is optional but highly recommended. With that, you
can quickly bring your cluster to a clean state after running the different OVN
[setup scripts][ovnsetups]. If you are using Vagrant 1.8.0 or newer, you can
use the built-in [vagrant snapshot][vgsnap] commands instead of the ones
that the [sahara][] plugin offers. I find it that using [sahara][] is
faster and works well in all versions of Vagrant. Life is full of choices, so
I will show you how to use both.

Vagrant plugin **vagrant-cachier** is optional. By using it you will make it
quicker to provision the VMS.

### Provisioning Steps

    $ git clone https://github.com/flavio-fernandes/just-ovn-nodes.git
    $ cd just-ovn-nodes

#### Edit the file **provisioning/virtualbox.conf.yml**

Adjust the parameters **ovn_repo** and **ovn_branch** to pick up the version of OVS/OVN you want. If you use the default, it will pick up a branch from my forked GitHub OVS repo that is a replica of original OVS master, but not the latest and greatest. If greatest and latest is what you want, simply use these values:

    ovn_repo: https://github.com/openvswitch/ovs.git
    ovn_branch: master

By default, there will be 1 OVN database node and 3 compute nodes in the setup.
However, node compute3 will not start automatically, unless you change its **autostart** parameter, or explicitly call **vagrant up compute3**. If you feel the need for having more compute nodes,
by all means, go ahead! The changes for accomplishing that are simple.
Do a search for the word _compute_ in these two files, and follow your
intuition on what needs to be done:
(1) _Vagrantfile_; (2) _provisioning/virtualbox.conf.yml_

If you want the OVN database node to also be used as a compute node, make sure
to set the **install_ovn_controller** parameter to _yes_.

Since we are not provisioning CMS, the VMS require a _lot less_ memory.
In the provisioning steps, the OVN database VM (aka central) will build packages and
store them in the directory _provisioning/pkgs_. All other VMS will simply install these
packages instead of having to build OVN from scratch.

    $ vagrant up
    # or ...
    $ time vagrant up central compute{1,2,3}

If you made it here, it is time for a quick coffee break. :)
Just to give you a ballpark idea: using my Macbook Pro (late 2015 model), the initial provisioning
takes a little over 12 minutes.

#### Optional: install Wireshark

It is always fun being able to look at the packets as _tenant ports_ talk to each other
across different
compute nodes. If you agree, go ahead and install Wireshark on the various nodes, by invoking the
script I made part of the repo. It will grab the latest from **[ppa:wireshark-dev/stable][wsppa]**,
so it can dissect packets that are encapsulated by [Geneve][].

**Note:** When prompted about " **Should non-superusers be able to capture packets?** ",
make sure to select " <**yes**> "

    $ vagrant ssh central   # and also maybe compute{1,2,3}
    vagrant@central:~$ /vagrant/provisioning/setup-wireshark.sh
    vagrant@central:~$ exit

#### Take snapshot now

At this point the VMs are ready to start the OVN (and OVS) processes, so you can do anything
you want. I would highly recommend taking a snapshot, so you can easily revert back to this
state and always have a fresh cluster to play with.

    # snapshot vms using sahara
    $ vagrant sandbox on

    # or ...

    # snapshot vms using build in command
    $ vagrant snapshot save freshAndClean

#### VM topology

{{< figure src="img/just-ovn-nodes/just-ovn-nodes-net-topology.jpg" title="" >}}

    eth0: management, used by Vagrant
    eth1: underlay network, interconnects tenant ports via tunnel
    eth2: added as part of the provider network (br-provider)

The topology is very simple, as you can see above. By
modifying the values in
**provisioning/virtualbox.conf.yml** you can control what eth1 and eth2 addresses are
configured for each of the VMs.

### Start OVN cluster 

At this point, you should start OVN cluster by running the script from the _OVN db_ VM (aka central):

    # Note: if you do not provide vagrant with the VM that you want to
    #       ssh into, it will connect to central, since it is
    #       configured as primary in Vagranfile
    $ vagrant ssh
    vagrant@central:~$ /vagrant/scripts/setup-ovn-cluster.sh

The output will look like this:

{{< gist anonymous a54e9289b0838b9391fd30d4b58d7536 >}}

**Side note:** A trick used to _remotely_ configure and start OVS + OVN-controller
in all the compute nodes from the central VM is defined in [scripts/helper-functions][rpcsh].
**OVN-controller** in each one of the compute nodes knows where the Southbound DB is
located through the **external-ids:ovn-remote**, in the open_vswitch database.
That value is set by **ovs_open_vswitch_setup** function in
file [provisioning/ovn-common-functions][ovnRemote] as shown here:

    ovs-vsctl set open_vswitch . external-ids:ovn-remote="$OVN_SB_REMOTE"

#### Connect to each VM

Open separate terminal sessions and ssh to all VMS, so you can inspect their flow tables.
OVN related info can be obtained at the central VM. OVS ports used to represent tenant VMs
are added using Linux namespaces, similar to what is done in OpenStack.

    $ vagrant ssh compute1   ;  # or central, or compute2

At this point, you can try out the various scripts in [/vagrant/scripts/tutorial][ovnsetups].
You will need to run them from the _central_ node.

Output of **ovn-sbctl show**

    $ vagrant ssh 
    vagrant@central:~$ sudo ovn-sbctl show
    Chassis "compute1"
        hostname: "compute1.ovn.dev"
        Encap geneve
            ip: "192.168.33.31"
    Chassis "compute2"
        hostname: "compute2.ovn.dev"
        Encap geneve
            ip: "192.168.33.32"
    Chassis "compute3"
        hostname: "compute3.ovn.dev"
        Encap geneve
            ip: "192.168.33.33"


Here is an example of what to expect when executing setup.sh for
the **env1** script:

    $ vagrant ssh central
    vagrant@central:~$ ls /vagrant/scripts/tutorial
    env1  env4  env4_2vlans  l3_basic  l3_nat
    vagrant@central:~$ /vagrant/scripts/tutorial/env1/setup.sh

    vagrant@central:~$ sudo ovn-nbctl show
    switch 219d372b-07ea-459b-a639-f02c22d72055 (sw0)
        port sw0-port2
            addresses: ["00:00:00:00:00:02"]
        port sw0-port1
            addresses: ["00:00:00:00:00:01"]

    vagrant@central:~$ sudo ovn-sbctl show
    Chassis "compute1"
        hostname: "compute1.ovn.dev"
        Encap geneve
            ip: "192.168.33.31"
        Port_Binding "sw0-port1"
    Chassis "compute2"
        hostname: "compute2.ovn.dev"
        Encap geneve
            ip: "192.168.33.32"
        Port_Binding "sw0-port2"
    Chassis "compute3"
        hostname: "compute3.ovn.dev"
        Encap geneve
            ip: "192.168.33.33"



### Ryan Moats' tools

My friend and new colleague
[regXboi][] has put together some handy tools for parsing and
sorting  various output from a system running OVN. These tools are available at his
[GitHub repo][regXboiRepo]:

    git clone https://github.com/jayhawk87/ovn-doc-tools.git

Here is a sample output of some of these handy tools:

    $ vagrant ssh central
    vagrant@central:~$ cd /vagrant/
    vagrant@central:/vagrant$ git clone https://github.com/jayhawk87/ovn-doc-tools.git
    vagrant@central:/vagrant$ ./scripts/setup-ovn-cluster.sh
    vagrant@central:/vagrant$ ./scripts/tutorial/env1/setup.sh
    vagrant@central:/vagrant$ cd ovn-doc-tools/
    vagrant@central:/vagrant/ovn-doc-tools$ sudo ./dump-ovn-nb.sh
    ## You'll see: https://gist.github.com/ded27fc5875a84a69c7e5e37207b2257

    vagrant@central:/vagrant/ovn-doc-tools$ sudo ./dump-ovn-sb.sh
    ## You'll see: https://gist.github.com/5f639d40513354cde26ae5b41e080306

    vagrant@central:/vagrant$ exit

    $ vagrant ssh compute1
    vagrant@compute1:~$ cd /vagrant/ovn-doc-tools/
    vagrant@compute1:/vagrant/ovn-doc-tools$ sudo ./dump-ovs.sh
    ## You'll see: https://gist.github.com/e198bb738c14f49e9e40ab7f5e677e42

### Getting cluster back to fresh and clean state

Assuming you created a snapshot after doing the initial provisioning of the
VMS, this is how you can restore them back to that state:

    # snapshot vms using sahara
    $ vagrant sandbox rollback

    # or ...

    # snapshot vms using build in command
    $ vagrant snapshot restore --no-provision freshAndClean

### show-ns-ports.sh

In order to quickly know the mappings of a namespace, the logical ports and their
bindings, consider using the **[show-ns-ports.sh][]** script. Here is an example
of what to expect, after configuring the cluster with the **l3_nat** setup script.

    $ vagrant sandbox rollback
    $ vagrant ssh
    vagrant@central:~$ /vagrant/scripts/setup-ovn-cluster.sh
    vagrant@central:~$ /vagrant/scripts/tutorial/l3_nat/setup.sh

    vagrant@central:~$ /vagrant/scripts/show-ns-ports.sh
    ns3 in compute1 has eth0 with 192.168.2.2 matches lsp bar1
    ns1 in compute1 has eth0 with 192.168.1.2 matches lsp foo1
    ns2 in compute2 has eth0 with 172.16.1.2 matches lsp alice1

### Looking at packets with [Geneve][] encapsulation

If you did the step on installing Wireshark, continue on from the commands
mentioned in **show-ns-ports.sh** above, and check out the packets across
the compute nodes.

    # ssh with X11 forwarding
    $ vagrant ssh compute1 -- -XY
    # start Wireshark and ignore warnings about "swrast"
    vagrant@compute1:~$ wireshark > /dev/null 2>1 &

    # there should be 2 namespaces in compute1, as mentioned in the
    # output of the show-ns-ports.sh above. Start a shell inside ns1
    # and start ping from there to alice1 (172.16.1.2)
    vagrant@compute1:~$ sudo ip netns exec ns1 bash
    root@compute1:~# ping 172.16.1.2

Back in the Wireshark window, start capture on eth1 of compute1. You should
be able to see the ICMP packets, as shown below:

{{< figure src="img/just-ovn-nodes/just-ovn-nodes-wireshark.jpg" title="" >}}

#### A few interesting facts about the Geneve portion of the capture

As we are capturing a ping between foo1 and alice1, we can correlate the
fields in the Geneve capture as follows. Note that this is the ICMP reply,
from alice1 to foo1 (through router R1).

To understand these, look at the doc called [ovn-architecture][OVNArchit],
under the Tunnel encapsulations section. Note that soon that may move
to a separate file (called **ovn/OVN-DESIGN.md**), as shown
in [this patch][ovnDesign].

     VNI: 00 00 03  <== tunnel key ; should be LS foo
     class: 01 02 
     type: 00 
     len: 01 (8 bytes, including class + type + len + ingress + egress)
     00 01  <== ingress port (logical) ; should be the patch port from R1 to foo
     00 02  <== egress port (logical) ; should be foo1

So, does it look right? To find out, we need to ensure that tunnel key 3
belongs to the logical switch that has foo1 (ie foo):

    vagrant@central:~$ sudo ovn-nbctl show
        switch 051478a4-6a2c-4ed7-9a10-cf71e26a8bb5 (foo)
            port foo1
                addresses: ["f0:00:00:01:02:03 192.168.1.2"]
            port rp-foo
                addresses: ["00:00:01:01:02:03"]
    ...

    vagrant@central:~$ sudo ovn-sbctl list Datapath_Binding
    ...
    _uuid               : 5c770508-c892-43ff-bd75-4b1406865667
    external_ids        : {logical-switch="051478a4-6a2c-4ed7-9a10-cf71e26a8bb5"}
    tunnel_key          : 3  <=== yeah!
    ...

Next, we need to see what logical ports 1 and 2 for logical switch foo mean.
This is not all that exciting since the only 2 ports in LS foo are foo1 and rp-foo.

    vagrant@central:~$ sudo ovn-sbctl list Port_Binding
    ...
    _uuid               : 14d97a99-82fb-44e0-8ad0-f0132ca5afca
    chassis             : []  <== distributed L3, belongs to no chassis
    datapath            : 5c770508-c892-43ff-bd75-4b1406865667  <== foo
    logical_port        : rp-foo
    mac                 : ["00:00:01:01:02:03"]
    options             : {peer=foo}
    parent_port         : []
    tag                 : []
    tunnel_key          : 1  <=== yeah!
    type                : patch    <=== patch port from R1
    ...
    _uuid               : a7dde17e-f438-43ea-9b9a-2a2183e3b153
    chassis             : ac722b9f-7e81-4ffe-b0f0-94ab9e43c2b1  <== compute1
    datapath            : 5c770508-c892-43ff-bd75-4b1406865667  <== foo
    logical_port        : "foo1"
    mac                 : ["f0:00:00:01:02:03 192.168.1.2"]
    options             : {}
    parent_port         : []
    tag                 : []
    tunnel_key          : 2  <=== yeah!
    type                : ""
    ...


    vagrant@central:~$ OVS_DBDIR=${OVS_DBDIR:-/var/run/openvswitch} ; sudo ovsdb-client dump unix:${OVS_DBDIR}/ovnsb_db.sock

    Chassis table
    _uuid                                encaps                                 external_ids             hostname           name       nb_cfg vtep_logical_switches
    ------------------------------------ -------------------------------------- ------------------------ ------------------ ---------- ------ ---------------------
    ac722b9f-7e81-4ffe-b0f0-94ab9e43c2b1 [473b8b74-1b40-4f1d-9fc0-13b21a4c0953] {ovn-bridge-mappings=""} "compute1.ovn.dev" "compute1" 0      []
    34538460-514f-4a95-83a0-a20eafa07816 [b6a37b5c-ab01-484f-824d-61fa1bb7f814] {ovn-bridge-mappings=""} "compute2.ovn.dev" "compute2" 0      []
    66ce0b20-d3a8-4756-afdd-5e18c12a11e2 [fa48a4db-ccf8-4da6-8930-dba78a1d817c] {ovn-bridge-mappings=""} "compute3.ovn.dev" "compute3" 0      []
    ...


### Hooking up port from namespace to br-int

Lastly, I would like to spend a few lines talking about the
various ways that OVS ports can get scoped by namespace, and how OVN is able
to map a logical port to an OVS port, at any given compute node (aka chassis).

For starters, read [this page][ovsPortNs] to see the variations on how
this is accomplished. Then, look at the script **[create-ns-port.sh][]**. After considering
creating an [internal][usingOvsInternal] port in OVS,
I thought that using veth is nicer for
debugging, so we can easily attach Wireshark to the corresponding veth interface outside
the namespace.

To map a logical port to a physical OVS port, OVN relies on the **external-ids:iface-id**
field, set during the port creation and [shown here][ovsExternalId].

In order to have a unique id for the namespaces used, the script requires you to use the
central VM. With that, it leverages the [file lock][flock] API, through the function
[get_next_counter_value][].

### Closing blurb

All in all, I hope this offers an easy way into the vast world of OVN and how you can
get your feet wet with it.
As you can assume, there are many extremely smart and friendly people
in the OVS+OVN community. As I learn from them and do OVN experiments of my own,
I will post more related blogs on this site. A deeper dive into the various logical
and OpenFlow rules is high on my todo list. Your feedback is very welcome, always! The
[about link][aboutff] at the top of this page should give you a bunch
of ways you can reach me.

## Some -- incomplete list of -- links related to this topic you might want
to visit:

  - [OVS Orbit](http://ovsorbit.benpfaff.org/), by Ben Pfaff
  - [Introduction to OVN](http://galsagie.github.io/2015/04/20/ovn-1/), by Gal
  - networking-ovn's Vagrant for [deploying O/S cluster][networkingOvnVagrant]
  - Russell's [blogs on OVN](https://blog.russellbryant.net/category/ovs/ovn/)
  - Kyle's [blogs on OVN](https://www.siliconloons.com/categories/ovn/)
  - [OVN Architecture][OVNArchit]
  - Guru's [repo in installing OVN][guruOvnNs]
  - Miguel's [Blog pages](http://www.ajo.es/)
  - Miguel's [repo on OVS experiments](https://github.com/mangelajo/ovs-experiments)
  - Scott Lowe's [blogs on OVN](http://blog.scottlowe.org/tags/#OVN)
  - Okay Google, [lookup OVN for me](http://bfy.tw/6zEN)

[OVN]: https://networkheresy.wordpress.com/2015/01/13/ovn-bringing-native-virtual-networking-to-ovs/ "Open Virtual Network"
[O/S]: http://www.openstack.org/ "OpenStack"
[OSComm]: http://www.openstack.org/community/ "OpenStack Community"
[OVNArchit]: http://openvswitch.org/support/dist-docs/ovn-architecture.7.html "Open Virtual Network Architecture"
[networking-ovn]: http://docs.openstack.org/developer/networking-ovn/readme.html "networking-ovn - OpenStack Neutron integration with OVN"
[ml2]: http://www.slideshare.net/mestery/modular-layer-2-in-openstack-neutron "Modular Layer 2 In OpenStack Neutron"
[osPast]: http://www.flaviof.com/blog/tag/openstack.html "Past adventures with OpenStack"
[divAndC]: https://en.wikipedia.org/wiki/Divide_and_conquer_algorithms "Divide and Conquer"
[ovsTest]: https://github.com/openvswitch/ovs/tree/master/tests "OVS and OVN unit tests"
[OVN-Tutorial.md]: https://github.com/openvswitch/ovs/blob/master/tutorial/OVN-Tutorial.md "OVN Tutorial -- using sandbox"
[ovnSandbox]: https://gist.githubusercontent.com/anonymous/08f3d07aff4a26e368da3e5e12c7e3a1/raw/386f48218221b8a1ba2a70642c2204e540133937/gistify194222.txt "OVS sandbox example"
[lxc]: https://linuxcontainers.org/lxc/introduction/ "Linux namespace"
[ovnAcl]: https://blog.russellbryant.net/2015/10/22/openstack-security-groups-using-ovn-acls/ "Russell's OVN ACL"
[Vagrant]: https://www.vagrantup.com/ "Vagrant"
[Geneve]: https://datatracker.ietf.org/doc/draft-gross-geneve/ "Geneve encapsulation"
[just-ovn-nodes]: https://github.com/flavio-fernandes/just-ovn-nodes "Just OVN Nodes"
[guruOvnNs]: https://github.com/shettyg/ovn-namespace "Installing OVN from source -- Guru"
[petCattle]: http://www.it20.info/2012/12/vcloud-openstack-pets-and-cattle/ "Pet vs cattle"
[networkingOvnVagrant]: https://github.com/openstack/networking-ovn/tree/master/vagrant "Automatic deployment using Vagrant and VirtualBox"
[aboutff]: http://www.flaviof.com/blog/pages/about-me.html "About flaviof"
[vgsnap]: https://www.vagrantup.com/docs/cli/snapshot.html "Vagrant snapshot"
[sahara]: https://github.com/jedi4ever/sahara "Vagrant plugin sahara"
[show-ns-ports.sh]: https://raw.githubusercontent.com/flavio-fernandes/just-ovn-nodes/master/scripts/show-ns-ports.sh "show-ns-ports.sh"
[ovnsetups]: https://github.com/flavio-fernandes/just-ovn-nodes/tree/master/scripts/tutorial "OVN setup scripts"
[wsppa]: https://launchpad.net/~wireshark-dev/+archive/ubuntu/stable "Wireshark Developers team"
[rpcsh]: https://github.com/flavio-fernandes/just-ovn-nodes/blob/56ed2d1e4b0df3bff537742b5d95cabff4a45b6f/scripts/helper-functions#L20 "rpcsh"
[ovnRemote]: https://github.com/flavio-fernandes/just-ovn-nodes/blob/56ed2d1e4b0df3bff537742b5d95cabff4a45b6f/provisioning/ovn-common-functions#L45 "ovs_open_vswitch_setup"
[regXboi]: https://github.com/jayhawk87 "Ryan Moats"
[regXboiRepo]: https://github.com/jayhawk87/ovn-doc-tools "Ryan's ovn-doc-tools"
[ovsPortNs]: http://www.opencloudblog.com/?p=66 "Interconnecting Namespaces"
[create-ns-port.sh]: https://github.com/flavio-fernandes/just-ovn-nodes/blob/a8531151dc4b15902dd51c03f0163c5de3e986a0/scripts/create-ns-port.sh "create-ns-port.sh"
[usingOvsInternal]: https://github.com/flavio-fernandes/just-ovn-nodes/commit/b67d2dd62b230a065139d1531c58fcb1e7329753 "Using internal OVS port instead of veth pair"
[flock]: http://www.kfirlavi.com/blog/2012/11/06/elegant-locking-of-bash-program/ "File lock"
[get_next_counter_value]: https://github.com/flavio-fernandes/just-ovn-nodes/blob/a8531151dc4b15902dd51c03f0163c5de3e986a0/scripts/helper-functions#L53 "get_next_counter_value"
[ovnDesign]: https://patchwork.ozlabs.org/patch/652013/ "OVN-DESIGN.md document"
[ovsExternalId]: https://github.com/flavio-fernandes/just-ovn-nodes/blob/a8531151dc4b15902dd51c03f0163c5de3e986a0/scripts/create-ns-port.sh#L64 "OVS port external-id"
