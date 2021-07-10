+++
author = "flaviof"
categories = ["main"]
date = "2021-07-02T17:01:00-05:00"
tags = ["ovn", "python"]
title = "OpenStack Port Forwarding using OVN"
+++

Implementation notes for Port Forwarding feature in ML2/OVN

<!--more-->

I had a blast implementing [port forwarding][pf] (PF) under the [module layer 2][ML2] plug-in for the [OVN][] Networking service ([Neutron][neutron])
in [OpenStack][O/S].

After a few months of planning and testing, the work was merged in time for the [Victoria][] release.
It is open-source all the way: the [reviews and commits][pf_commits] are publically available via Gerrit.
While I was the one who submitted the changes, there is no way it would have happened without the amazing
support from my co-workers at Red Hat and Neutron community.

{{< figure src="img/port-forwarding/openstack-port-forwarding-commits.jpg" title="openstack ML2/ovn pf commits" >}}

Before I forget most of the details, I decided to write this page with info on how this feature works.
We already have a [design spec][pf_design] written, so my goal here is to add a few pointers and commands for anyone interested
in using it.

### What is [Floating IP] Port Forwarding?

**"Port Forwarding (PF) allows a public (aka [floating IP][fip]) (FIP) to be shared by multiple virtual machines, based on the incoming protocol and port number."**
In other words, multiple servers can be exposed using the same FIP, based on a protocol+port configuration. The way it accomplishes that is
by using what is commonly known as a [firewall pinhole][pinhole]. The [Neutron spec on PF][neutron_pf_spec] does a good job of explaining it a bit further.

### Getting Port Forwarding by leveraging Load Balancers

Load Balancers (LBs) offer a natural way to expose a set of internal addresses from a single external [virtual IP] address (VIP).
In this context, we can safely assume that VIP and FIP are the same thing.
Come to think of it, PF is nothing but a simplification of LBs, where the "set" of internal addresses has just a single entry.
Thus, implementing this feature involved nothing else but coming up with a basic implementation of OVN LBs, where each FIP+protocol+port tuple maps to
one internal address+protocol+port.
Once that is done, OVN takes care of all the needed plumbing in the datapath, including the [destination network address translation (DNAT)][dnat]
to make PF work.
Look for **Load_Balancer TABLE** in the [ovn-nb man pages][ovn_nb] for some great documentation on how that table is used.

## Trying it out

**OVN Workshop**: As I was thinking of a nice way of getting a sandbox deployment to use for this page, I recalled an
awesome talk that [Daniel][daniel] and [Sławek][slawek] did during the [Open Infrastructure Summit 2020][infra_2020].
So I just, forked the [environment they used][daniel_vagrants] to easily show off the port forwarding feature.
If you are not aware of the talk, definitely give it a try:

[![Hands-on Workshop](https://img.youtube.com/vi/fZmMaQf36fg/0.jpg)](https://www.youtube.com/watch?v=fZmMaQf36fg?t=1790 "Troubleshooting OpenStack Neutron with ML2/OVN backend driver")

In any case, let's get started with an OpenStack cluster running Victoria or a later release. If you need to create one, consider using the
Vagrant + devstack script [kept under this link][osp_devstack]. The [README file][osp_devstack_readme] provides all the info needed.

```
git clone https://github.com/flavio-fernandes/ovn-openstack.git && cd ovn-openstack
vagrant up  ; # stacking will take ~17 minutes... be patient
vagrant ssh
```

Once inside the VM, try an example where one external IP exposes ssh access to two VMs by mapping their TCP port 22
from external ports 2221 and 2222:

```
openstack server create --flavor m1.nano --image $IMAGE_ID \
    --key-name demo -f value -c id \
    --nic net-id=private,v4-fixed-ip=10.0.0.11 vm1

openstack server create --flavor m1.nano --image $IMAGE_ID \
    --key-name demo -f value -c id \
    --nic net-id=private,v4-fixed-ip=10.0.0.12 vm2 --wait

openstack port set --name vm1p \
    $(openstack port list --server vm1 -f value -c ID)
openstack port set --name vm2p \
    $(openstack port list --server vm2 -f value -c ID)

FIP=172.24.4.111
FIP_ID=$(openstack floating ip create \
    --floating-ip-address ${FIP} public -f value -c id)

openstack floating ip port forwarding create -f value -c id \
    --internal-ip-address 10.0.0.11 --internal-protocol-port 22 \
    --port vm1p --external-protocol-port 2221 --protocol tcp $FIP_ID

openstack floating ip port forwarding create -f value -c id \
    --internal-ip-address 10.0.0.12 --internal-protocol-port 22 \
    --port vm2p --external-protocol-port 2222 --protocol tcp $FIP_ID
```

Note: The excerpt above assumes that image, flavor, key, and networks have already been created.
That will be the case if you used the vagrant deployment mentioned.
Look at [central.sh][] for details on that.

Next, verify that it worked by trying the commands below.

```bash
SSH="ssh -i ~/id_rsa_demo -o StrictHostKeyChecking=no"
SSH="${SSH} -o UserKnownHostsFile=/dev/null cirros@${FIP}"
for PRT in 2221 2222; do  \
    ${SSH} -p ${PRT} -- "echo hello from \$(hostname) via ${FIP} port ${PRT}" \
    2>&1 | grep -v 'known hosts'
done

hello from vm1 via 172.24.4.111 port 2221
hello from vm2 via 172.24.4.111 port 2222
```

#### PF in OpenStack

Taking a look at the Neutron logs, we can get a good idea of the main components exercised by the commands above.
If you are interested in seeing the entire log, take a look at [this gist link][server.log].

The log has all sorts of interesting info. In particular to PF, check out what happens then a **forwarding create** command takes place:
```
Jul 02 21:41:47 central neutron-server[92593]: DEBUG neutron.api.v2.base [None req-f7c03e90-84c2-4851-8ffc-35bdfc7f417c admin admin] Request body: {'port_forwarding': {'external_port': 2222, 'internal_port_id': '8dacc668-ce3e-4892-96a8-d968dfb92f00', 'protocol': 'tcp', 'internal_ip_address': '10.0.0.12', 'internal_port': 22}} {{(pid=92593) prepare_request_body /opt/stack/neutron/neutron/api/v2/base.py:729}}
...
Jul 02 21:41:47 central neutron-server[92593]: DEBUG neutron_lib.callbacks.manager [None req-f7c03e90-84c2-4851-8ffc-35bdfc7f417c admin admin] Notify callbacks ['neutron.services.portforwarding.drivers.ovn.driver.OVNPortForwarding._handle_notification-334183'] for port_forwarding, after_create {{(pid=92593) _notify_loop /usr/local/lib/python3.8/dist-packages/neutron_lib/callbacks/manager.py:192}}
Jul 02 21:41:47 central neutron-server[92593]: INFO neutron.services.portforwarding.drivers.ovn.driver [None req-f7c03e90-84c2-4851-8ffc-35bdfc7f417c admin admin] CREATE for port-forwarding tcp vip 172.24.4.111:2222 to 10.0.0.12:22
Jul 02 21:41:47 central neutron-server[92593]: DEBUG ovsdbapp.backend.ovs_idl.transaction [None req-f0622324-c1c8-4897-b130-a998ed1f9321 None None] Running txn n=1 command(idx=0): LbAddCommand(lb=pf-floatingip-c4842074-9558-49c6-b003-4a3a6c260162-tcp, vip=172.24.4.111:2222, ips=10.0.0.12:22, protocol=tcp, may_exist=True, columns={'external_ids': {'neutron:device_owner': 'port_forwarding_plugin', 'neutron:fip_id': 'c4842074-9558-49c6-b003-4a3a6c260162', 'neutron:router_name': 'neutron-aa4793a7-3557-4e49-9022-09e3e32ce403'}}) {{(pid=92593) do_commit /usr/local/lib/python3.8/dist-packages/ovsdbapp/backend/ovs_idl/transaction.py:90}}
Jul 02 21:41:47 central neutron-server[92593]: DEBUG ovsdbapp.backend.ovs_idl.transaction [None req-f0622324-c1c8-4897-b130-a998ed1f9321 None None] Running txn n=1 command(idx=1): LrLbAddCommand(router=neutron-aa4793a7-3557-4e49-9022-09e3e32ce403, lb=pf-floatingip-c4842074-9558-49c6-b003-4a3a6c260162-tcp, may_exist=True) {{(pid=92593) do_commit /usr/local/lib/python3.8/dist-packages/ovsdbapp/backend/ovs_idl/transaction.py:90}}
...
Jul 02 21:41:47 central neutron-server[92593]: INFO neutron.wsgi [None req-f7c03e90-84c2-4851-8ffc-35bdfc7f417c admin admin] 192.168.150.100 "POST /v2.0/floatingips/c4842074-9558-49c6-b003-4a3a6c260162/port_forwardings HTTP/1.1" status: 201  len: 449 time: 0.2649674
```

In order to make content a little easier to read, I will be using an abbreviation for the UUIDS and some aliases.
Less is more. :)

```bash
$ abbrev() { a='[0-9a-fA-F]' b=$a$a c=$b$b; sed "s/$b-$c-$c-$c-$c$c$c//g"; } ; \
  alias ovn-nbctl='sudo ovn-nbctl' ; \
  alias ovn-sbctl='sudo ovn-sbctl'
```

Let's dig up some more details on how this works. First, let's look at the key OpenStack objects configured.

```bash
$ openstack network list -f yaml | abbrev
- ID: 297ba2
  Name: private
  Subnets:
  - 5c6ff5
  - 8abc66
- ID: 92f92a
  Name: public
  Subnets:
  - b18b5f
  - bd9add

$ openstack port list --server vm1 -f yaml | abbrev
  ID: d441a4f0
  Name: vm1p
  - Fixed IP Addresses:
    - ip_address: 10.0.0.11
      subnet_id: 5c6ff57b
    - ip_address: fdf0:7fca:d4d1:0:f816:3eff:fe15:92df
      subnet_id: 8abc669f
  MAC Address: fa:16:3e:15:92:df
  Status: ACTIVE

$ openstack port list --server vm2 -f yaml | abbrev
  ID: 8dacc668
  Name: vm2p
  - Fixed IP Addresses:
    - ip_address: 10.0.0.12
      subnet_id: 5c6ff57b
    - ip_address: fdf0:7fca:d4d1:0:f816:3eff:feb0:3fbf
      subnet_id: 8abc669f
  MAC Address: fa:16:3e:b0:3f:bf
  Status: ACTIVE

$ which jq || sudo apt install -y jq
$ openstack floating ip list -f json | jq . | abbrev
[
  {
    "ID": "c4842074",
    "Floating IP Address": "172.24.4.111",
    "Fixed IP Address": null,
    "Port": null,
    "Floating Network": "92f92ab3",
    "Project": "3c1d5087f3ac4a268b7c72bc31f3a0f4"
  }
]

$ [ -n "${FIP_ID}" ] || FIP_ID=$(openstack floating ip list -f value -c ID)
$ openstack floating ip port forwarding list $FIP_ID -f json | jq . | abbrev
[
  {
    "ID": "501e5a25",
    "Internal Port ID": "8dacc668",
    "Internal IP Address": "10.0.0.12",
    "Internal Port": 22,
    "External Port": 2222,
    "Protocol": "tcp",
    "Description": ""
  },
  {
    "ID": "d644e2f6",
    "Internal Port ID": "d441a4f0",
    "Internal IP Address": "10.0.0.11",
    "Internal Port": 22,
    "External Port": 2221,
    "Protocol": "tcp",
    "Description": ""
  }
]
```

Notice how the floating IP above does not have a "Fixed IP Address", nor "Port". That is
a key difference in the port forwarding feature, as the same FIP is
used by one or many "floating ip port forwarding" entries.
You can see the [database model][neutron_pf_spec] to represent that:

```
$ mysql
mysql> use neutron
mysql> show create table portforwardings;
CREATE TABLE `portforwardings` (
  `id` varchar(36) NOT NULL,
  `floatingip_id` varchar(36) NOT NULL,
  `external_port` int NOT NULL,
  `internal_neutron_port_id` varchar(36) NOT NULL,
  `protocol` varchar(40) NOT NULL,
  `socket` varchar(36) NOT NULL,
  `standard_attr_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_port_forwardings0floatingip_id0external_port0protocol` (`floatingip_id`,`external_port`,`protocol`),
  UNIQUE KEY `uniq_port_forwardings0internal_neutron_port_id0socket0protocol` (`internal_neutron_port_id`,`socket`,`protocol`),
  UNIQUE KEY `uniq_portforwardings0standard_attr_id` (`standard_attr_id`),
  CONSTRAINT `portforwardings_ibfk_1` FOREIGN KEY (`floatingip_id`) REFERENCES `floatingips` (`id`) ON DELETE CASCADE,
  CONSTRAINT `portforwardings_ibfk_2` FOREIGN KEY (`internal_neutron_port_id`) REFERENCES `ports` (`id`) ON DELETE CASCADE,
  CONSTRAINT `portforwardings_ibfk_3` FOREIGN KEY (`standard_attr_id`) REFERENCES `standardattributes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3
mysql> exit;
```

#### PF in OVN NB Database

From OVN's angle, these are the tables populated by the ML2 plugin for providing PF.
Notice how the OVN router does not have a NAT item for the FIP (172.24.4.111). That is
because the floating IP is not explicitly "associated" when used for port forwarding.
The only NAT for the router here is the SNAT for serving the 10.0.0.0/26 (private)
network via lrp-a01c3b (172.24.4.20 in public).

```bash
$ ovn-nbctl show | abbrev
switch ad714f (neutron-297ba2) (aka private)
    port bae455
        type: localport
        addresses: ["fa:16:3e:cc:40:07 10.0.0.2 fdf0:7fca:d4d1:0:f816:3eff:fecc:4007"]
    port d441a4 (aka vm1p)
        addresses: ["fa:16:3e:15:92:df 10.0.0.11 fdf0:7fca:d4d1:0:f816:3eff:fe15:92df"]
    port 8dacc6 (aka vm2p)
        addresses: ["fa:16:3e:b0:3f:bf 10.0.0.12 fdf0:7fca:d4d1:0:f816:3eff:feb0:3fbf"]
    port 397435
        type: router
        router-port: lrp-397435
    port 18d577
        type: router
        router-port: lrp-18d577
switch bdd4c9 (neutron-92f92a) (aka public)
    port 44eb81
        type: localport
        addresses: ["fa:16:3e:79:61:ea"]
    port provnet-c0458a
        type: localnet
        addresses: ["unknown"]
    port a01c3b
        type: router
        router-port: lrp-a01c3b
router 25ee01 (neutron-aa4793) (aka router1)
    port lrp-a01c3b
        mac: "fa:16:3e:f7:37:0b"
        networks: ["172.24.4.20/24", "2001:db8::1b6/64"]
        gateway chassis: [24837e]
    port lrp-397435
        mac: "fa:16:3e:f5:38:f1"
        networks: ["fdf0:7fca:d4d1::1/64"]
    port lrp-18d577
        mac: "fa:16:3e:d3:8c:20"
        networks: ["10.0.0.1/26"]
    nat 4de53c
        external ip: "172.24.4.20"
        logical ip: "10.0.0.0/26"
        type: "snat"

$ ovn-nbctl --column _uuid,name,addresses,external_ids list logical_switch_port vm1p | abbrev
_uuid        : 5051449c
addresses    : ["fa:16:3e:15:92:df 10.0.0.11 fdf0:7fca:d4d1:0:f816:3eff:fe15:92df"]
external_ids : {"neutron:cidrs"="10.0.0.11/26 fdf0:7fca:d4d1:0:f816:3eff:fe15:92df/64",
                "neutron:device_id"="4ca39c15",
                "neutron:device_owner"="compute:nova",
                "neutron:network_name"=neutron-297ba21a,
                "neutron:port_name"=vm1p,
                "neutron:project_id"="3c1d5087f3ac4a268b7c72bc31f3a0f4",
                "neutron:revision_number"="6",
                "neutron:security_group_ids"="4a66544f"}

$ ovn-nbctl --column _uuid,name,addresses,external_ids list logical_switch_port vm2p | abbrev
_uuid        : b70a85ab
addresses    : ["fa:16:3e:b0:3f:bf 10.0.0.12 fdf0:7fca:d4d1:0:f816:3eff:feb0:3fbf"]
external_ids : {"neutron:cidrs"="10.0.0.12/26 fdf0:7fca:d4d1:0:f816:3eff:feb0:3fbf/64",
                "neutron:device_id"="819fc854",
                "neutron:device_owner"="compute:nova",
                "neutron:network_name"=neutron-297ba21a,
                "neutron:port_name"=vm2p,
                "neutron:project_id"="3c1d5087f3ac4a268b7c72bc31f3a0f4",
                "neutron:revision_number"="6",
                "neutron:security_group_ids"="4a66544f"}
```

The following two tables contain all the rows needed in order to satisfy OpenStack's PF. Pay close attention to the "vips" and
"protocol" attributes in the load_balancer table:

```bash
$ ovn-nbctl list load_balancer | abbrev
_uuid            : c1a805
external_ids     : {"neutron:device_owner"=port_forwarding_plugin,
                    "neutron:fip_id"="c4842074",
                    "neutron:revision_number"="4",
                    "neutron:router_name"=neutron-aa4793a7}
health_check     : []
ip_port_mappings : {}
name             : pf-floatingip-c4842074-tcp
protocol         : tcp
vips             : {"172.24.4.111:2221"="10.0.0.11:22",
                    "172.24.4.111:2222"="10.0.0.12:22"}

$ ovn-nbctl list logical_router | abbrev
_uuid            : 25ee01
enabled          : true
external_ids     : {"neutron:availability_zone_hints"="", "neutron:gw_port_id"="a01c3b", "neutron:revision_number"="6",
                    "neutron:router_name"=router1}
load_balancer    : [c1a805]
name             : neutron-aa4793
nat              : [4de53c]
options          : {}
policies         : []
ports            : [37d8be, ccd1dc, ea00b8]
static_routes    : [05c7bc, 9e753c]
```

Even though there are two database entries in OpenStack to represent the two PFs, only one row in OVN is needed since both are
using the same protocol (i.e. TCP). OVN LBs can have multiple values in its "vips" column, and that is where the mappings for PF are
managed by ML2/OVN. Lastly, we have the logical router (LR) table, which contains a reference to the load balancer. Openflow rules
used to respond to ARPs on behalf of the FIP happen from the logical router's datapath because the LB is referenced by the LR.
You can see these rules in the "Openflow" section below.

## Code overview

The file [pf_plugin.py][] is the glue that holds the pieces of this feature together at the Neutron codebase.
From there, the [PF OVN driver][pf_ovn_driver] receives the [relevant callbacks][pf_callbacks_ovn] and takes the appropriate
action for the OVN side of things.

Since pf_plugin in Neutron handles the validation and database common to all ML2 implementations,
the changes in this part of the code were minimal. They were mostly related to making PF capable of using ovn-router instead
of the legacy l3-agent-router, as well as using registry callbacks instead of pushing RPCs. You can get a very good sense of these
changes [by looking at this commit][pf_callbacks_pf_plugin].

On the ML2/OVN side, a small number of additions were needed besides [the new driver][pf_ovn_driver] itself. They are part of
the [core feature commit][pf_ovn_core]. In there, see how [maintenance.py][] now needs to differentiate FIPs used for PF from FIPs
associated with a single fixed address. Another ML2/OVN component that needed changes was [ovn_db_sync.py][], which is used for repairing
potential discrepancies between Neutron and OVN databases. [For starters, ovn_db_sync.py][ovn_db_sync.py_fip_aware]
needed to start paying attention to the load balancers table in OVN used to represent the PFs in Neutron. See below for more info on using
that tool, even though the usage syntax is not changed at all due to PF support.

And that is pretty much all there is!

## Testing

A lot of care, love, and attention was put into PF tests to ensure it remains working as time goes by. Even though the tests
run as part of the CI/CD ([unit][unit_job_ovn], [functional][functional_job_ovn], [tempest][tempest_job_ovn]), you can always run them manually.
Here is how:

#### Unit and functional
```bash
$ cd /opt/stack/neutron
$ tox -e py3 -- test_port_forwarding
$ tox -e dsvm-functional -- test_port_forwarding ; # Note: some L3 agent tests do not apply to ovn-router!
$ tox -e dsvm-functional -- ovsdb.test_ovn_db_sync
  ...
  dsvm-functional: commands succeeded
  congratulations :)
```

#### Tempest
A few extra tempest [tests were added][pf_tempest]. They can be run as follows.
```bash
$ cd /opt/stack/tempest/ && \
  tempest run --config-file etc/tempest.conf --regex test_port_forwardings
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_associate_2_port_forwardings_to_floating_ip [2.733917s] ... ok
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_associate_port_forwarding_to_2_fixed_ips [2.445890s] ... ok
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_associate_port_forwarding_to_port_with_fip [2.439997s] ... ok
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_associate_port_forwarding_to_used_floating_ip [1.627926s] ... ok
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_info_in_fip_details [1.536234s] ... ok
{0} neutron_tempest_plugin.api.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_life_cycle [2.335318s] ... ok
{1} neutron_tempest_plugin.scenario.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_editing_and_deleting_tcp_rule [127.669750s] ... ok
{1} neutron_tempest_plugin.scenario.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_editing_and_deleting_udp_rule [66.878624s] ... ok
{1} neutron_tempest_plugin.scenario.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_to_2_fixed_ips [90.960107s] ... ok
{1} neutron_tempest_plugin.scenario.test_port_forwardings.PortForwardingTestJSON.test_port_forwarding_to_2_servers [107.509035s] ... ok
```

## Database Repair

In the unlikely event that Neutron and OVN databases become out of sync, the damage may cause PF to break.
[Enhancements to the repair][ovn_db_sync.py] tool -- also known as neutron-ovn-db-sync-util -- are in place to fix that. See the
example below for how to use it, as we forcefully break PF and ensure that the repair is done right.

```bash
$ echo ${SSH} -p ${PRT} -- "echo hello from \$(hostname) via ${FIP} port ${PRT}"
ssh -i ~/id_rsa_demo -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null cirros@172.24.4.111 -p 2222 -- echo hello from $(hostname) via 172.24.4.111 port 2222

$ ${SSH} -p ${PRT} -- "echo hello from \$(hostname) via ${FIP} port ${PRT}" 2>&1 | grep -v "known hosts"
hello from vm2 via 172.24.4.111 port 2222

$ ovn-nbctl lb-list
UUID                                    LB                  PROTO      VIP                  IPs
c1a805d0-f7fc-4fe7-8a43-5ac5ec2739c2    pf-floatingip-c4    tcp        172.24.4.111:2221    10.0.0.11:22
                                                            tcp        172.24.4.111:2222    10.0.0.12:22
$ # Let's grab load balancer uuid and delete it
$ LB=$(ovn-nbctl --bare --column _uuid find load_balancer "external_ids:\"neutron:device_owner\"=port_forwarding_plugin")
$ ovn-nbctl lb-del $LB

$ timeout 10 ${SSH} -p ${PRT} -- "echo hello from \$(hostname) via ${FIP} port ${PRT}" 2>&1 | grep -v "known hosts"
Terminated

$ ps auxww | grep -oh "neutron-server.*" | head -1
neutron-server --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ML2/ML2_conf.ini
$ CONFS=$(ps auxww | grep -oh "neutron-server.*" | head -1 | cut -d' ' -f2-)

$ sudo neutron-ovn-db-sync-util ${CONFS} --log-file=/tmp/util.log \
  --ovn-neutron_sync_mode log

$ grep WARN /tmp/util.log | grep floating
WARNING neutron.plugins.ML2.drivers.ovn.mech_driver.ovsdb.ovn_db_sync [None req-5a5c7f1b-78f0-4285-ac6a-e3dd1a63294d None None] Router aa4793a7-3557-4e49-9022-09e3e32ce403 floating ips [{'id': 'c4842074-9558-49c6-b003-4a3a6c260162', 'tenant_id': '3c1d5087f3ac4a268b7c72bc31f3a0f4', 'floating_ip_address': '172.24.4.111', 'floating_network_id': '92f92ab3-5f74-4ace-bd8d-66322b83784c', 'router_id': 'aa4793a7-3557-4e49-9022-09e3e32ce403', 'port_id': None, 'fixed_ip_address': None, 'status': 'ACTIVE', 'standard_attr_id': 48, 'description': '', 'qos_policy_id': None, 'port_details': None, 'dns_domain': '', 'dns_name': '', 'port_forwardings': [{'external_port': 2222, 'protocol': 'tcp', 'internal_ip_address': '10.0.0.12', 'internal_port': 22}, {'external_port': 2221, 'protocol': 'tcp', 'internal_ip_address': '10.0.0.11', 'internal_port': 22}], 'tags': [], 'created_at': '2021-07-02T21:40:05Z', 'updated_at': '2021-07-02T21:41:47Z', 'revision_number': 4, 'project_id': '3c1d5087f3ac4a268b7c72bc31f3a0f4'}] found in Neutron but not in OVN
WARNING neutron.plugins.ML2.drivers.ovn.mech_driver.ovsdb.ovn_db_sync [None req-5a5c7f1b-78f0-4285-ac6a-e3dd1a63294d None None] Router aa4793a7-3557-4e49-9022-09e3e32ce403 port forwarding for floating ips ['c4842074-9558-49c6-b003-4a3a6c260162'] Neutron out of sync or missing in OVN

$ # fix it
$ sudo neutron-ovn-db-sync-util ${CONFS} --log-file=/tmp/util.log \
  --ovn-neutron_sync_mode repair

$ sudo rm /tmp/util.log ; \
  sudo neutron-ovn-db-sync-util ${CONFS} --log-file=/tmp/util.log \
    --ovn-neutron_sync_mode log && \
  grep WARN /tmp/util.log | grep -c floating
0

$ ovn-nbctl lb-list
UUID                                    LB                  PROTO      VIP                  IPs
67b6a3a3-5651-43d5-9d07-68d58d20bf4f    pf-floatingip-c4    tcp        172.24.4.111:2221    10.0.0.11:22
                                                            tcp        172.24.4.111:2222    10.0.0.12:22

$ timeout 10 ${SSH} -p ${PRT} -- "echo hello from \$(hostname) via ${FIP} port ${PRT}" 2>&1 | grep -v "known hosts"
hello from vm2 via 172.24.4.111 port 2222
```

## Openflow

The rules show how PF is accomplished by OVN via OVS. Take a look at the output below to see how that applies to this
specific example.

```bash
$ ovn-sbctl dump-flows | grep -e ${FIP} -e 2221 -e 2222 -e Datapath | abbrev
Datapath: "neutron-297ba2" aka "private" (0d05ca)  Pipeline: ingress
  table=19(ls_in_l2_lkup      ), priority=75   , match=(flags[1] == 0 && arp.op == 1 && arp.tpa == { 10.0.0.1, 172.24.4.111}), action=(outport = "18d577"; output;)
  table=19(ls_in_l2_lkup      ), priority=75   , match=(flags[1] == 0 && arp.op == 1 && arp.tpa == { 172.24.4.111}), action=(outport = "397435"; output;)

Datapath: "neutron-92f92a" aka "public" (4ed073)  Pipeline: ingress
  table=19(ls_in_l2_lkup      ), priority=75   , match=(flags[1] == 0 && arp.op == 1 && arp.tpa == { 172.24.4.20, 172.24.4.111}), action=(clone { outport = "provnet-c0458a"; output; }; outport = "a01c3b"; output;)

Datapath: "neutron-aa4793" aka "router1" (d5b75d)  Pipeline: ingress
  table=3 (lr_in_ip_input     ), priority=90   , match=(inport == "lrp-18d577" && arp.tpa == 172.24.4.111 && arp.op == 1), action=(eth.dst = eth.src; eth.src = fa:16:3e:d3:8c:20; arp.op = 2; /* ARP reply */ arp.tha = arp.sha; arp.sha = fa:16:3e:d3:8c:20; arp.tpa = arp.spa; arp.spa = 172.24.4.111; outport = "lrp-18d577"; flags.loopback = 1; output;)
  table=3 (lr_in_ip_input     ), priority=90   , match=(inport == "lrp-397435" && arp.tpa == 172.24.4.111 && arp.op == 1), action=(eth.dst = eth.src; eth.src = fa:16:3e:f5:38:f1; arp.op = 2; /* ARP reply */ arp.tha = arp.sha; arp.sha = fa:16:3e:f5:38:f1; arp.tpa = arp.spa; arp.spa = 172.24.4.111; outport = "lrp-397435"; flags.loopback = 1; output;)
  table=3 (lr_in_ip_input     ), priority=90   , match=(inport == "lrp-a01c3b" && arp.tpa == 172.24.4.111 && arp.op == 1 && is_chassis_resident("cr-lrp-a01c3b")), action=(eth.dst = eth.src; eth.src = fa:16:3e:f7:37:0b; arp.op = 2; /* ARP reply */ arp.tha = arp.sha; arp.sha = fa:16:3e:f7:37:0b; arp.tpa = arp.spa; arp.spa = 172.24.4.111; outport = "lrp-a01c3b"; flags.loopback = 1; output;)
  table=4 (lr_in_defrag       ), priority=100  , match=(ip && ip4.dst == 172.24.4.111), action=(ct_next;)
  table=6 (lr_in_dnat         ), priority=120  , match=(ct.est && ip && ip4.dst == 172.24.4.111 && tcp && tcp.dst == 2221 && is_chassis_resident("cr-lrp-a01c3b")), action=(ct_dnat;)
  table=6 (lr_in_dnat         ), priority=120  , match=(ct.est && ip && ip4.dst == 172.24.4.111 && tcp && tcp.dst == 2222 && is_chassis_resident("cr-lrp-a01c3b")), action=(ct_dnat;)
  table=6 (lr_in_dnat         ), priority=120  , match=(ct.new && ip && ip4.dst == 172.24.4.111 && tcp && tcp.dst == 2221 && is_chassis_resident("cr-lrp-a01c3b")), action=(ct_lb(10.0.0.11:22);)
  table=6 (lr_in_dnat         ), priority=120  , match=(ct.new && ip && ip4.dst == 172.24.4.111 && tcp && tcp.dst == 2222 && is_chassis_resident("cr-lrp-a01c3b")), action=(ct_lb(10.0.0.12:22);)
```

```bash
$ sudo ovs-ofctl -O OpenFlow13 --names dump-flows br-int | cut -d',' -f3- | grep -e ${FIP} -e 2221 -e 2222
 table=11, n_packets=0, n_bytes=0, priority=90,arp,reg14=0x1,metadata=0x2,arp_tpa=172.24.4.111,arp_op=1 actions=move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[],set_field:fa:16:3e:d3:8c:20->eth_src,set_field:2->arp_op,move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[],set_field:fa:16:3e:d3:8c:20->arp_sha,move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[],set_field:172.24.4.111->arp_spa,set_field:0x1->reg15,load:0x1->NXM_NX_REG10[0],resubmit(,32)
 table=11, n_packets=7, n_bytes=294, priority=90,arp,reg14=0x2,metadata=0x2,arp_tpa=172.24.4.111,arp_op=1 actions=move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[],set_field:fa:16:3e:f7:37:0b->eth_src,set_field:2->arp_op,move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[],set_field:fa:16:3e:f7:37:0b->arp_sha,move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[],set_field:172.24.4.111->arp_spa,set_field:0x2->reg15,load:0x1->NXM_NX_REG10[0],resubmit(,32)
 table=11, n_packets=0, n_bytes=0, priority=90,arp,reg14=0x4,metadata=0x2,arp_tpa=172.24.4.111,arp_op=1 actions=move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[],set_field:fa:16:3e:f5:38:f1->eth_src,set_field:2->arp_op,move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[],set_field:fa:16:3e:f5:38:f1->arp_sha,move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[],set_field:172.24.4.111->arp_spa,set_field:0x4->reg15,load:0x1->NXM_NX_REG10[0],resubmit(,32)
 table=12, n_packets=88, n_bytes=17880, priority=100,ip,metadata=0x2,nw_dst=172.24.4.111 actions=ct(table=13,zone=NXM_NX_REG11[0..15])
 table=14, n_packets=5, n_bytes=370, priority=120,ct_state=+new+trk,tcp,metadata=0x2,nw_dst=172.24.4.111,tp_dst=2222 actions=group:2
 table=14, n_packets=0, n_bytes=0, priority=120,ct_state=+new+trk,tcp,metadata=0x2,nw_dst=172.24.4.111,tp_dst=2221 actions=group:1
 table=14, n_packets=83, n_bytes=17510, priority=120,ct_state=+est+trk,tcp,metadata=0x2,nw_dst=172.24.4.111,tp_dst=2222 actions=ct(table=15,zone=NXM_NX_REG11[0..15],nat)
 table=14, n_packets=0, n_bytes=0, priority=120,ct_state=+est+trk,tcp,metadata=0x2,nw_dst=172.24.4.111,tp_dst=2221 actions=ct(table=15,zone=NXM_NX_REG11[0..15],nat)
 table=27, n_packets=2, n_bytes=84, priority=75,arp,reg10=0/0x2,metadata=0x3,arp_tpa=172.24.4.111,arp_op=1 actions=clone(set_field:0x1->reg15,resubmit(,32)),set_field:0x3->reg15,resubmit(,32)
 table=27, n_packets=0, n_bytes=0, priority=75,arp,reg10=0/0x2,metadata=0x1,arp_tpa=172.24.4.111,arp_op=1 actions=set_field:0x2->reg15,resubmit(,32)
```

## Final Words

There is much more to OVN load balancers (e.g. [health checking][ovn_octavia_hm]) that go beyond what the port forwarding functionality needs.
In order to tap into the world of OVN load balancing from OpenStack, check out [ovn-octavia-provider][].
The PF changes for managing load balancers outside [ovn-octavia-provider][] are conscientious of that and include an [integration test][ovn_octavia_integration]
used in CI to ensure they coexist in harmony.

For OpenStack usage cases where the number of available FIPs is small and multiple VMs need to be accessed from the provider network, the sharing of FIPs is a big deal.
It is great that OVN can solve this need through load balancers and that we now have that leveraged via ML2/OVN, bringing the [parity gap][gap]
with ML2/OVS even closer.

Please do not be shy to point out anything on this page that needs improvement by leaving a comment. Cheers!

[pf]: https://blueprints.launchpad.net/neutron/+spec/port-forwarding "Neutron’s Floating IP port forwarding"
[OVN]: https://networkheresy.wordpress.com/2015/01/13/ovn-bringing-native-virtual-networking-to-ovs/ "Open Virtual Network"
[neutron]: https://docs.openstack.org/neutron/latest/ "Neutron"
[O/S]: http://www.openstack.org/ "OpenStack"
[Victoria]: https://releases.openstack.org/victoria/ "Victoria"
[networking-ovn]: http://docs.openstack.org/developer/networking-ovn/readme.html "networking-ovn - OpenStack Neutron integration with OVN"
[ML2]: http://www.slideshare.net/mestery/modular-layer-2-in-openstack-neutron "Modular Layer 2 In OpenStack Neutron"
[pf_commits]: https://review.opendev.org/q/topic:%22ovn%252Fport_forwarding%22+(status:open%20OR%20status:merged) "ML2/OVN Port Forwarding"
[pf_design]: https://docs.openstack.org/neutron/latest/contributor/internals/ovn/port_forwarding.html "ML2/OVN Port forwarding"
[fip]: https://www.rdoproject.org/networking/difference-between-floating-ip-and-private-ip/ "Floating IP"
[pinhole]: https://en.wikipedia.org/wiki/Firewall_pinhole "Firewall pinhole"
[neutron_pf_spec]: https://specs.openstack.org/openstack/neutron-specs/specs/rocky/port-forwarding.html "Port Forwarding API"
[infra_2020]: https://www.openshift.com/blog/check-out-our-talks-at-the-virtual-open-infrastructure-summit-2020 "Talks at the Virtual Open Infrastructure Summit 2020"
[daniel_vagrants]: https://github.com/danalsan/vagrants/tree/master/devstack-workshop "OpenInfra Summit workshop - Devstack with OVN backend in Neutron"
[dnat]: https://docs.openstack.org/newton/networking-guide/intro-nat.html "Destination Network Address Translation"
[ovn_nb]: https://www.ovn.org/support/dist-docs/ovn-nb.5.html "OVN_Northbound database schema"
[daniel]: https://github.com/danalsan "Daniel Alvarez Sanchez"
[slawek]: https://github.com/slawqo "Sławek Kapłoński"
[osp_devstack]: https://github.com/flavio-fernandes/ovn-openstack "ovn-openstack repo for devstack"
[central.sh]: https://github.com/flavio-fernandes/ovn-openstack/blob/master/central.sh "Devstack deploy script central.sh"
[server.log]: https://gist.github.com/flavio-fernandes/284cec2742ca3e7a582f2667c47271ce "Neutron server.log gist"
[osp_devstack_readme]: https://github.com/flavio-fernandes/ovn-openstack/blob/master/README.md "ovn-openstack repo readme.md"
[pf_plugin.py]: https://github.com/openstack/neutron/blob/102c442bcfa39074787e3292818880ecf238ac61/neutron/services/portforwarding/pf_plugin.py "neutron/services/portforwarding/pf_plugin.py"
[pf_ovn_driver]: https://github.com/openstack/neutron/commit/d74f409c82fb73601b859cd6b243bbbc97b49153#diff-59ad911e55c561605812a57a1d8af2c236d1ffac4a70279abd123a2b3a2ebe11 "neutron/services/portforwarding/drivers/ovn/driver.py"
[pf_callbacks_ovn]: https://github.com/openstack/neutron/commit/d74f409c82fb73601b859cd6b243bbbc97b49153#diff-59ad911e55c561605812a57a1d8af2c236d1ffac4a70279abd123a2b3a2ebe11R175 "port forwarding callbacks entry point in OVN driver"
[pf_callbacks_pf_plugin]: https://github.com/openstack/neutron/commit/102c442bcfa39074787e3292818880ecf238ac61#diff-4717a13f0edace736ffa87555c29411b12b6cd6d44d336a25bf68076d42e07f9 "neutron/services/portforwarding/pf_plugin.py"
[pf_ovn_core]: https://review.opendev.org/c/openstack/neutron/+/741303 "pf_ovn_core"
[maintenance.py]: https://github.com/openstack/neutron/commit/d74f409c82fb73601b859cd6b243bbbc97b49153#diff-cbcdc928b31e8562100a24d73912316f2d0c67d18cac681a546ee8ad6ebb384f "neutron/plugins/ML2/drivers/ovn/mech_driver/ovsdb/maintenance.py"
[ovn_db_sync.py_fip_aware]: https://github.com/openstack/neutron/commit/d74f409c82fb73601b859cd6b243bbbc97b49153#diff-fd82c3bf33b55a717bc8f3708ad987e53d71093718e321a471788fdff01df465 "neutron/plugins/ML2/drivers/ovn/mech_driver/ovsdb/ovn_db_sync.py"
[ovn_db_sync.py]: https://review.opendev.org/c/openstack/neutron/+/743772 "feature support under ovn_db_sync"
[unit_job_ovn]: https://zuul.opendev.org/t/openstack/job/openstack-tox-py38 "openstack-tox-py38"
[functional_job_ovn]: https://zuul.opendev.org/t/openstack/job/neutron-functional-with-uwsgi "neutron-functional-with-uwsgi"
[tempest_job_ovn]: https://zuul.opendev.org/t/openstack/job/neutron-tempest-plugin-scenario-ovn "neutron-tempest-plugin-scenario-ovn"
[pf_tempest]: https://review.opendev.org/c/openstack/neutron-tempest-plugin/+/755760 "Add more port_forwarding tests"
[ovn_octavia_hm]: https://review.opendev.org/c/openstack/ovn-octavia-provider/+/713253 "OVN Octavia Provider support for health monitoring"
[ovn-octavia-provider]: https://opendev.org/openstack/ovn-octavia-provider "OVN Octavia Provider"
[ovn_octavia_integration]: https://review.opendev.org/c/openstack/ovn-octavia-provider/+/743189 "OVN Octavia Integration test"
[gap]: https://review.opendev.org/c/openstack/neutron/+/740955/6/doc/source/ovn/gaps.rst "ML2/OVN and ML2/OVS parity gap"
