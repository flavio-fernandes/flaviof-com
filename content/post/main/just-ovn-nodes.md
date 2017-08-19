+++
author = "flaviof"
co-author = "Matthew Kassawara"
categories = ["main"]
date = "2016-07-28T01:39:42-04:00"
tags = ["ovn"]
title = "just ovn nodes"
series = "Hacking OVN"
+++

Deploy OVN in minutes, independent of a _Cloud Management System_ (aka CMS) such as OpenStack.

<!--more-->

Normally, _Open Virtual Network_ (aka [OVN][]) works in conjunction with a CMS.
_OpenStack_ (aka [O/S][]), a popular CMS that [many][OSComm] companies use, implements OVN
via [module layer 2][ml2] plug-in for the Networking service (neutron).

I played a bit with OpenStack in [past adventures][osPast], but recently shifted my focus
to OVN. In order to improve my OVN skills, I found it more productive to [divide and conquer][divAndC]
by leaving the CMS, particularly OpenStack, out of the picture.

# OVN in a Sandbox

You can easily deploy OVN using the sandbox, similar to the [unit tests][ovsTest]. For more
information on the sandbox, see [OVN-Tutorial.md][]. For an example of using OVN within the
sandbox, see [output below][ovnSandbox]:

{{< gist anonymous 08f3d07aff4a26e368da3e5e12c7e3a1 >}}

However, the sandbox has some limitations:

  - The fake (aka dummy) OVS datapath offers only a subset of the functionality available in
    the kernel, [ACL and Conntrack][ovnAcl], to name a few.

  - Unable to use Linux [lxc][] to provide namespaces (isolated IP stack instances).
    OVS ports in the sandbox cannot be scoped by their own TCP/IP stack, thus preventing
    use of powerful tools like _ping_ to generate traffic and see the rules in action.
    Similarly, isolated ARP and routing tables are not possible.
    Instead, you must use commands like **ovs-appctl netdev-dummy/receive**,
    as shown at the end of the [sandbox][ovnSandbox] example.

## Making the Case for just-ovn-nodes

Thus, to provide something more _realistic_ than the sandbox, but yet not as _complex_ as an
[OVN + networking-ovn + O/S deployment][networkingOvnVagrant], you can simply use
**[just-ovn-nodes][]**. Using [Vagrant][], this repository
gives us an automated way of assembling all the pieces for a multi-node deployment with OVN which
serves as a "throwaway" setup ([cattle][petCattle]) for quickly trying something out or as a
starting place for creating a ([pet][petCattle]) cluster for OVN development.
Bear in mind I'm not the only one who has reached this serendipity. :) Folks like
Gurucharan Shetty -- undoubtedly one of my awesome gurus --
have a [similar repository][guruOvnNs] 
available. So be sure to look around too.

### Prerequisites

Dependencies for using [just-ovn-nodes][]:

- Hypervisor (compatible with Vagrant)
- Git
- Vagrant
- Vagrant plug-ins (see below)

#### Vagrant plug-ins

    for p in vagrant-reload sahara vagrant-cachier ; do \
       vagrant plugin install $p
    done

Vagrant plug-in **vagrant-reload** enables the provisioning process to reboot
a VM after updating the kernel to a version that supports [Geneve][] encapsulation
and other features necessary for OVN operation.

Vagrant plug-in **sahara** is optional but highly recommended. It enables returning
your cluster to a clean state after running the different OVN [setup scripts][ovnsetups].
If using Vagrant 1.8.0 or newer, you can simply use the built-in [vagrant snapshot][vgsnap]
commands instead of the ones that the [sahara][] plug-in offers. However, I find [sahara][]
faster and works well on all versions of Vagrant. Life is full of choices, so I will
explain how to use both.

Vagrant plug-in **vagrant-cachier** is optional and increases speed of the provisioning
process.

### Provisioning

    $ git clone https://github.com/flavio-fernandes/just-ovn-nodes.git
    $ cd just-ovn-nodes

#### Edit the file **provisioning/virtualbox.conf.yml**

Adjust the parameters **ovn_repo** and **ovn_branch** to pick up the appropriate version of OVS/OVN. If you use the default, it will pick up a branch from my forked GitHub OVS repository that is a replica of original OVS master, but not the latest and greatest. If you want the latter, simply use these values:

    ovn_repo: https://github.com/openvswitch/ovs.git
    ovn_branch: master

By default, the cluster contains one OVN database node and three compute nodes.
However, node _compute3_ does not start automatically unless you change its **autostart** parameter
or explicitly call **vagrant up compute3**. If you want more compute nodes, by all means, go ahead!
The changes for accomplishing that are simple: perform a search for the word _compute_ in the
following two files and follow your intuition on what to modify.
(1) _Vagrantfile_; (2) _provisioning/virtualbox.conf.yml_

If you also want to use the OVN database node as a compute node, set the **install_ovn_controller**
parameter to _yes_.

Since we are not provisioning a CMS, the VMs require a _lot less_ memory.
In the provisioning steps, the OVN database VM (central) builds packages and
stores them in the directory _provisioning/pkgs_. All other VMs simply install these
packages instead of having to build OVN from scratch.

    $ vagrant up
    # or ...
    $ time vagrant up central compute{1,2,3}

Congrats for making it this far! :)
Just to give you a ballpark idea, with my Macbook Pro (late 2015 model), the initial
provisioning takes a little over 12 minutes.

#### Optional: Install Wireshark

I find it fun to look at the packets as _tenant ports_ talk to each other across different
compute nodes. If you agree, go ahead and install Wireshark on the various nodes by invoking the
script included in the repository that grabs the latest version from
**[ppa:wireshark-dev/stable][wsppa]** supporting [Geneve][] encapsulation.

**Note:** When prompted about " **Should non-superusers be able to capture packets?** ",
select " <**yes**> "

    $ vagrant ssh central   # and also maybe compute{1,2,3}
    vagrant@central:~$ /vagrant/provisioning/setup-wireshark.sh
    vagrant@central:~$ exit

#### Take a Snapshot Now

At this point, the VMs are ready to start the OVN (and OVS) processes, so you can do anything.
I highly recommend taking a snapshot so you can easily revert back to this clean state.

    # snapshot vms using sahara
    $ vagrant sandbox on

    # or ...

    # snapshot vms using build in command
    $ vagrant snapshot save freshAndClean

#### VM Topology

{{< figure src="img/just-ovn-nodes/just-ovn-nodes-net-topology.jpg" title="" >}}

    eth0: management, used by Vagrant
    eth1: underlay network, interconnects tenant ports via tunnel
    eth2: added as part of the provider network (br-provider)

By default, the topology is very simple. You can control the IP addresses for the _eth1_
and _eth2_ interfaces in each VM by modifying the values in **provisioning/virtualbox.conf.yml**

### Start OVN Cluster

At this point, start OVN cluster by running the script from the _OVN db_ VM (aka central):

    # note: if you do not provide vagrant with the vm name, it
    #       will connect to central, because it is configured
    #       as primary in vagrantfile.
    $ vagrant ssh
    vagrant@central:~$ /vagrant/scripts/setup-ovn-cluster.sh

The output looks like the following:

{{< gist anonymous a54e9289b0838b9391fd30d4b58d7536 >}}

**Note:** A trick used to _remotely_ configure and start OVS + OVN-controller
on all the compute nodes from the central VM is defined in [scripts/helper-functions][rpcsh].
**OVN-controller** in each of the compute nodes knows the location of the Southbound database
through **external-ids:ovn-remote** in the open_vswitch database. The **ovs_open_vswitch_setup**
function in [provisioning/ovn-common-functions][ovnRemote] sets this value:

    ovs-vsctl set open_vswitch . external-ids:ovn-remote="$OVN_SB_REMOTE"

#### Connect to Each VM

Open separate terminal sessions and SSH to each VM so you can inspect the flow tables. You can
obtain OVN information on the _central_ VM. OVS ports representing tenant VMs use Linux namespaces,
similar to OpenStack.

    $ vagrant ssh compute1   ;  # or central, or compute2

At this point, you can try out the various scripts in [/vagrant/scripts/tutorial][ovnsetups] from
the _central_ node.

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

Example output after executing **setup.sh** for the
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

### Ryan Moats' Tools

My friend and new colleague
[regXboi][] has put together some handy tools for parsing and
sorting various output from a system running OVN. You can find these tools in his
[GitHub repository][regXboiRepo]:

    git clone https://github.com/jayhawk87/ovn-doc-tools.git

Example output from some of these handy tools:

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

### Getting Cluster Back to “Fresh and Clean” State

Assuming you created a snapshot after initial provisioning of the VMs,
you can restore them to a fresh and clean state:

    # snapshot vms using sahara
    $ vagrant sandbox rollback

    # or ...

    # snapshot vms using build in command
    $ vagrant snapshot restore --no-provision freshAndClean

### show-ns-ports.sh

In order to quickly reveal the mappings of a namespace, the logical ports and their
bindings, consider using the **[show-ns-ports.sh][]** script. Example output after
configuring the cluster with the **l3_nat** setup script:

    $ vagrant sandbox rollback
    $ vagrant ssh
    vagrant@central:~$ /vagrant/scripts/setup-ovn-cluster.sh
    vagrant@central:~$ /vagrant/scripts/tutorial/l3_nat/setup.sh

    vagrant@central:~$ /vagrant/scripts/show-ns-ports.sh
    ns3 in compute1 has eth0 with 192.168.2.2 matches lsp bar1
    ns1 in compute1 has eth0 with 192.168.1.2 matches lsp foo1
    ns2 in compute2 has eth0 with 172.16.1.2 matches lsp alice1

### Inspecting Packets with [Geneve][] Encapsulation

If you installed Wireshark, continue from the commands in **show-ns-ports.sh**
and inspect the packets traversing the compute nodes.

    # ssh with X11 forwarding
    $ vagrant ssh compute1 -- -XY
    # start Wireshark and ignore warnings about "swrast"
    vagrant@compute1:~$ wireshark > /dev/null 2>&1 &

    # there should be 2 namespaces in compute1, as mentioned in the
    # output of the show-ns-ports.sh above. Start a shell inside ns1
    # and start ping from there to alice1 (172.16.1.2)
    vagrant@compute1:~$ sudo ip netns exec ns1 bash
    root@compute1:~# ping 172.16.1.2

In the Wireshark window, start a capture on the _eth1_ interface in _compute1_. You should
see the ICMP packets as follows:

{{< figure src="img/just-ovn-nodes/just-ovn-nodes-wireshark.jpg" title="" >}}

#### The Geneve Portion of the Capture

As we capture a _ping_ between _foo1_ and _alice1_, we can correlate the
fields in the Geneve capture as follows. Note that this is the ICMP reply,
from _alice1_ to _foo1_ through router _R1_.

To understand the output, see the tunnel encapsulations section of [ovn-architecture][OVNArchit].
This content may move to a separate file (**ovn/OVN-DESIGN.md**) according to [this patch][ovnDesign].

     VNI: 00 00 03  <== tunnel key ; should be LS foo
     class: 01 02 
     type: 00 
     len: 01 (8 bytes, including class + type + len + ingress + egress)
     00 01  <== ingress port (logical) ; should be the patch port from R1 to foo
     00 02  <== egress port (logical) ; should be foo1

So, does it look right? To find out, we need to ensure that tunnel key 3
belongs to the logical switch containing _foo1_ (aka _foo_):

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

Next, see what logical ports 1 and 2 for logical switch _foo_ mean.
Nothing particularly exciting because logical switch _foo_ only contains two ports:
_foo1_ and _rp-foo_.

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


### Connecting a Port from a Namespace to br-int

Lastly, I want spend some time discussing the various ways that namespaces can scope OVS
ports and how OVN can map a logical port to an OVS port on any given compute node (chassis).

First, read [this page][ovsPortNs] to see the variations on how this is accomplished. Next,
look at the script **[create-ns-port.sh][]**. After creating an [internal][usingOvsInternal]
port in OVS, I found using _veth_ more practical for debugging because we can easily attach
Wireshark to it.

To map a logical port to a physical OVS port, OVN relies on the **external-ids:iface-id**
field, set during the port creation and [shown here][ovsExternalId].

To have a unique id for the namespaces used, the script requires you to use the
central VM because it can leverage the [file lock][flock] API through the function
[get_next_counter_value][].

### Closing Blurb

All in all, I hope this content provides an easy way into the vast world of OVN in a simple
fashion. The OVN+OVS community contains many extremely smart and friendly people. As I learn from
them and do OVN experiments of my own, I shall post more blogs, particularly a deeper dive into
the various logical and OpenFlow rules. I appreciate your feedback.
The [about link][aboutff] at the top of this page should provide a bunch
of ways to can reach me.

## Some links related to this topic you might want to visit:

  - [OVS Orbit](http://ovsorbit.benpfaff.org/), by Ben Pfaff
  - [Introduction to OVN](http://galsagie.github.io/2015/04/20/ovn-1/), by Gal
  - networking-ovn's Vagrant for [deploying O/S cluster][networkingOvnVagrant]
  - Russell's [blogs on OVN](https://blog.russellbryant.net/category/ovs/ovn/)
  - Kyle's [blogs on OVN](https://www.siliconloons.com/categories/ovn/)
  - [OVN Architecture][OVNArchit]
  - Guru's [repository in installing OVN][guruOvnNs]
  - Miguel's [Blog pages](http://www.ajo.es/)
  - Miguel's [repository on OVS experiments](https://github.com/mangelajo/ovs-experiments)
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
[OVN-Tutorial.md]: https://github.com/openvswitch/ovs/blob/master/Documentation/tutorials/ovn-sandbox.rst "OVN Tutorial -- using sandbox"
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
[sahara]: https://github.com/jedi4ever/sahara "Vagrant plug-in sahara"
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
