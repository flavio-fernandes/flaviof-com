+++
author = "flaviof"
categories = ["main"]
date = "2020-11-15T17:01:00-05:00"
tags = ["bash", "ovn"]
title = "ddlog and OVN"
series = "Hacking OVN"
+++

My first encounter with ddlog integrated with ovn-northd 

<!--more-->

In a not distant future, OVN will be leveraging the power of ddlog to synchronize its
southbound and northbound databases, thanks to the awesome work done by Ben Pfaff,
Leonid Ryzhyk and others. I took some time at my Red Hat's day of learning to see how
that looks like and wrote some notes along the way.

# Installation

As explained in [Documentation/intro/install/general.rst][general.rst], [rust][rust]
is needed in order to use [ddlog][ddlog] with [ovn-northd-ddlog][ovn-northd-ddlog].
Here are the steps I took in order to have it working on a Centos 8 install:

```
$ # rust install
$ curl https://sh.rustup.rs -sSf > /tmp/rustup.sh

$ # make sure the file looks legit...
$ vi /tmp/rustup.sh

$ bash /tmp/rustup.sh

$ # check rustc version
$ source $HOME/.cargo/env
$ rustc --version
rustc 1.47.0 (18bf6b4f0 2020-10-07)
```

The script will give you choices for customizing the install, including the setting of the PATH
variable. As for installing the ddlog portion, only a tarball is needed:

```
$ # Note: OVN requires DDlog v0.30.0 or newer
$ curl -L -o /tmp/ddlog.tgz  \
  https://github.com/vmware/differential-datalog/releases/download/v0.30.0/ddlog-v0.30.0-20201027231514-linux.tar.gz
$ cd && tar xzf /tmp/ddlog.tgz
```

At this point, I changed **.bash_profile** and tried the ddlog command:

```
$ cat <<EOT >>~/.bash_profile

DDLOG_HOME="\${HOME}/ddlog"
export DDLOG_HOME
PATH="\${HOME}/.cargo/bin:\${DDLOG_HOME}/bin:\${PATH}"
export PATH
EOT


$ . ~/.bash_profile
$ ddlog --version
DDlog v0.30.0 (56b0da1837d7ec8ea227873d0e129f5dfca179a1)
Copyright (c) 2019-2020 VMware, Inc. (MIT License)
```

# hello world, meet ddlog 

Before getting into OVN, I tried a hello world version of ddlog to appreciate
what the fuss is all about. Here is a simple example I thought of doing after
reading https://hexgolems.com/2020/10/getting-started-with-ddlog/. There are a
few extra links I found useful at the bottom of this page.

```
mkdir hw ; cd hw

cat <<EOT > ./helloWorld.dl
function is_even_number(value: u32): bool { value % 2 == 0 }
input relation ANumber(name: string, value: u32)
output relation EvenNumber(name: string)
EvenNumber(name) :- ANumber(name, value), is_even_number(value).
EOT

cat <<EOT > ./helloWorld.dat
start;
insert ANumber("two", 2),
insert ANumber("two", 2),
insert ANumber("two", 2),
commit;
dump EvenNumber;
EOT

cat <<EOT > ./helloWorld.dat2
start;
insert ANumber("one", 1),
insert ANumber("ten", 10),
insert ANumber("five", 5),
insert ANumber("twelve", 12),
insert ANumber("three", 3);
commit;
dump EvenNumber;
EOT
```

Building helloWorld_ddlog:

```
$ ddlog -i helloWorld.dl && \
  (cd helloWorld_ddlog && cargo build --release)

$ ./helloWorld_ddlog/target/release/helloWorld_cli < helloWorld.dat
EvenNumber{.name = "two"}

$ ./helloWorld_ddlog/target/release/helloWorld_cli < helloWorld.dat2
EvenNumber{.name = "ten"}
EvenNumber{.name = "twelve"}
```

# Trying out ovn-northd-ddlog

I used my fork in github to pull in [Ben's current review][benDdlog] for ddlog. That includes changes
I did to [enhance meters in OVN ACL logs][fairMeters]. More on that below.

Take a [look here][ovndeps] if you need to see the prerequisites for building OVS and OVN.
After taking care of that, here is what I did in order to build OVN with northd-ddlog:

```
$ git clone --depth 1 https://github.com/openvswitch/ovs.git && \
  cd ovs

$ ./boot.sh && ./configure --enable-Werror && \
  time make -j$(($(nproc) + 1)) V=0 ; echo $?

$ cd .. && \
  git clone --depth 1 -b acl-meters.v5.ddlog \
  https://github.com/flavio-fernandes/ovn.git && cd ovn

$ ./boot.sh && ./configure --enable-Werror \
  --with-ovs-source=${PWD}/../ovs \
  --with-ddlog=${DDLOG_HOME}/lib --enable-ddlog-fast-build && \
  time make -j$(($(nproc) + 1)) V=0 ; echo $?
```

The **with-ddlog** param instructs OVN to build ovn-northd-ddlog. If ddlog is not installed,
or you just want the non-ddlog version of ovn-northd, simply omit that. The **enable-ddlog-fast-build** makes
compilation faster but will cause ovn-northd-ddlog to skip optimizations. Avoid using that flag outside development
deployments.

The core of ddlog in ovn-northd-ddlog lives in the file [ovn_northd.dl][ovn_northd.dl]. Ben did a great
job explaining the ins and outs of it when I asked for help on what would be needed to have the
[fair acl log meters][fairMeters] there. You can see that conversation in the
[ovs mailing list][benExplainsDdlog].

The changes in OVN to leverage ddlog are only in northd so far (not in ovn-controller).
Also, they are being done in a way that the non-ddlog version of northd is still available.
In order to determine which version of northd is used, the [ovn-ctl][ovn-ctl] script will check for the
**ovn-northd-ddlog** parameter. This is what it looks like to use ovn-northd-ddlog:

```
$ DDLG='--ovn-northd-ddlog=yes' ; \
  sudo /usr/share/ovn/scripts/ovn-ctl $DDLG start_northd
```

The ovn-northd tests [have a loop][testLoop] that exercises both versions, so either one can be used until we are ready to
cut the umbilical cord. Here is a sample output of how that looks like:

```
$ make check TESTSUITEFLAGS="--keywords=fair"
...
## ------------------------ ##
## ovn 20.09.90 test suite. ##
## ------------------------ ##

OVN northd

353: ovn-northd -- ACL fair Meters -- ovn-northd     ok
354: ovn-northd -- ACL fair Meters -- ovn-northd-ddlog ok

## ------------- ##
## Test results. ##
## ------------- ##

All 2 tests were successful.
```

There are still some rough edges in need of
polishing, but I am certain these will get resolved soon. If you are curious about that, take a look at the logs from
the [upstream OVN meeting of 12/Nov/20][ovnUpstreamMeeting].

Lastly, these links were super useful in getting acclimated with ddlog:

- [A Differential Datalog (DDlog) tutorial](https://github.com/vmware/differential-datalog/blob/master/doc/tutorial/tutorial.md)
- [Getting Started with DDlog ](https://hexgolems.com/2020/10/getting-started-with-ddlog/)
- [Learn Datalog Today](https://www.learndatalogtoday.org/)
- [DDlog program deep dive](http://deepdive.stanford.edu/writing-dataflow-ddlog#)

Cheers!

[general.rst]: https://github.com/blp/ovs-reviews/commit/f56dafa83d6da6dee48632954b951af6dc536cb7#diff-f2edc1bfe3739505036199b7993c18b4a3320ba4ca38b85c3e1fc4762c87529dR92 "ddlog install"
[rust]: https://www.rust-lang.org/tools/install "install rust"
[ddlog]: https://github.com/vmware/differential-datalog/ "ddlog repo"
[ovn-northd-ddlog]: https://github.com/flavio-fernandes/ovn/blob/356e0bc7b53a9b7352957442f97222e813d5be3d/northd/ovn-northd-ddlog.c
[benDdlog]: https://github.com/blp/ovs-reviews/tree/ddlog10 "Ben Pfaff ddlog10"
[fairMeters]: https://patchwork.ozlabs.org/project/ovn/cover/20201116154957.2443-1-flavio@flaviof.com/ "ACL Log Fair Meters"
[ovndeps]: https://github.com/flavio-fernandes/ovsdbapp_playground/blob/4f0590ba2e803573a1ad80211dc627e4670d1a64/Vagrantfile#L11-L25 "Dependencies for building ovs+ovn"
[ovn_northd.dl]: https://github.com/flavio-fernandes/ovn/blob/acl-meters.v5.ddlog/northd/ovn_northd.dl "ovn_northd.dl"
[benExplainsDdlog]: https://mail.openvswitch.org/pipermail/ovs-dev/2020-November/377104.html "Ben Pfaff talks about ddlog for ovn-northd"
[ovn-ctl]: https://github.com/flavio-fernandes/ovn/blob/f56dafa83d6da6dee48632954b951af6dc536cb7/utilities/ovn-ctl "ovn-ctl"
[testLoop]: https://github.com/flavio-fernandes/ovn/blob/f56dafa83d6da6dee48632954b951af6dc536cb7/tests/ovn-macros.at#L459-L465 "ovn-northd ddlog and non-ddlog test loop"
[ovnUpstreamMeeting]: https://eavesdrop.openstack.org/meetings/ovn_community_development_discussion/2020/ovn_community_development_discussion.2020-11-12-18.15.log.html "2020-11-12-18.15.log"