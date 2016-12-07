+++
author = "flaviof"
categories = ["main", "hacks"]
date = "2016-12-07T09:40:32-05:00"
tags = ["libvirt"]
title = "virsh show ifs"
+++

A handy script for showing the vms configured in libvirt.

<!--more-->

While playing with [virsh][], I'm always interested in finding out
the macs, networks and vnc port of the configured virtual machines.

Thus **[virsh_show_ifs][]**.

    #!/bin/bash

    for x in $(virsh list --all | awk '{ if (NR > 2 && $2 != "") {print $2} }') ; do \
        v=$(virsh vncdisplay $x 2> /dev/null || true)
        echo "vm name: $x vnc: ${v:--}"
        virsh domiflist $x | awk '{ if (NR > 2) {print $0} }'
    done


If this is useful to you, put it in your path.
And feel free to share it with your geek friends. :)

  [virsh]: http://libvirt.org/virshcmdref.html#viewing
  [virsh_show_ifs]: https://gist.githubusercontent.com/anonymous/53e04a414c0d653b0edc2d39d513b1a4/raw/7409bcde914a83eafe916871d725f98058d4dc88/gistify146068.txt
