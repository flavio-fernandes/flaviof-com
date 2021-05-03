+++
author = "flaviof"
categories = ["main", "hacks"]
date = "2019-11-22T22:22:22-05:00"
tags = ["bash", "libvirt"]
title = "vagrant libvirt provider"
+++

Stepping stones for getting Vagrant working on libvirt

<!--more-->

[Vagrant][] remains one of my favorite ways of getting a virtual
machine going. I use it on [libvirt][] based systems, so I need
vagrant libvirt install. There are a few
caveats in installing that plugin, so I thought of documenting it here.

The first -- and a bit unrelated -- thing you may need to worry about
when getting vms deployed is [nesting][]. I will not get into details
here, but these links can show you how:

- [KVM-based Nested Virtualization][nest1]
- [Enable the setting for Nested KVM][nest2]
- [Nested Virtualization in KVM on CentOS/RHEL][nest3]

Even though Vagrant installation is possible via *yum* / *apt*,
I have found that most distros lag on the chosen version.
Furthermore, I noticed that installing the [vagrant-libvirt][] plugin on
versions 2.2.4 or older is a bit of a [recipe for disaster][disaster].
My advice is to [download and install Vagrant][vagrantDownloads] 2.2.5 or
newer, as shown below.

### On Centos / RHEL Host

These commands worked fine when I used versions 7 or 8. Note that Centos/RHEL 8
uses *dnf* instead of *yum*, but *yum* is available as a symbolic link, so you
should not have to worry about it.

```
# basics
sudo yum install -y qemu-kvm wget

# make sure you have these installed before attempting to install
# the vagrant-libvirt  plugin
sudo yum install -y libvirt libvirt-devel ruby-devel gcc make

VER=2.2.6  ; # make sure to use a vagrant newer than 2.2.5
wget https://releases.hashicorp.com/vagrant/${VER}/vagrant_${VER}_x86_64.rpm
sudo rpm -Uvh vagrant_${VER}_x86_64.rpm
```

### On Debian / Ubuntu Host

```
sudo apt update
sudo apt install -y qemu-kvm wget ; # basics
sudo apt install -y libvirt-bin libvirt-dev firewalld build-essential

VER=2.2.6  ; # make sure to use a vagrant newer than 2.2.5
wget https://releases.hashicorp.com/vagrant/${VER}/vagrant_${VER}_x86_64.deb
sudo dpkg -i ./vagrant_2.2.6_x86_64.deb
```

### at last...
```
vagrant plugin install vagrant-libvirt
```

### Vagrant boxes

At this point, you should be able to tap into the vast world of vagrant
[boxes available to libvirt][boxes] providers. Stay safe and stick with
official or boxes you are familiar with. Something like
[centos/8](https://app.vagrantup.com/centos/boxes/8) or
[debian/jessie64](https://app.vagrantup.com/debian/boxes/jessie64)
are popular choices.

<center>**[https://app.vagrantup.com/boxes/search?provider=libvirt][boxes]**</center>

### Bonus material: sshfs

A convenient way of getting files shared between host and vm is by using sshfs
mount. The vagrant sshfs plugin makes using that easy. Here is how
to get that installed and an example Vagrantfile that uses it:

```
# See: https://github.com/dustymabe/vagrant-sshfs
vagrant plugin install vagrant-sshfs
```

A Vagrantfile that uses sshfs and a few other interesting knobs:

```
Vagrant.configure(2) do |config|
    vm_memory = ENV['VM_MEMORY'] || '4000'
    vm_cpus = ENV['VM_CPUS'] || '4'

    config.ssh.forward_agent = true
    config.vm.hostname = "myvm"
    ## config.vm.network "forwarded_port", guest: 80, host: 8080
    ## or use: vagrant ssh -- -L 0.0.0.0:8080:localhost:80

    ## config.vm.network "public_network", :dev => "bridge0", :mode => "bridge", :type => "bridge"
    config.vm.network "private_network", ip: "192.168.1.10"

    ## config.vm.box = "debian/jessie64"
    ## config.vm.box = "generic/ubuntu1804"
    ## config.vm.box = "centos/7"
    config.vm.box = "centos/8"

    # Mount /vagrant via sshfs
    config.vm.synced_folder File.expand_path("."), "/vagrant", sshfs_opts_append: "-o nonempty", disabled: false, type: "sshfs"

    config.vm.provider 'libvirt' do |lb|
        # Note: Tons of other knobs you can use here. For info on that, go to:
        # https://github.com/vagrant-libvirt/vagrant-libvirt/blob/master/README.md
        lb.nested = true
        lb.memory = vm_memory
        lb.cpus = vm_cpus
        lb.suspend_mode = 'managedsave'
    end
    config.vm.provider "virtualbox" do |vb|
       # Note: Tons of other knobs you can use here. For info on that, go to:
       # https://www.virtualbox.org/manual/ch08.html#vboxmanage-modifyvm
       vb.memory = vm_memory
       vb.cpus = vm_cpus
       vb.customize ["modifyvm", :id, "--nested-hw-virt", "on"]
       vb.customize ["modifyvm", :id, "--nictype1", "virtio"]
       vb.customize ["modifyvm", :id, "--nictype2", "virtio"]
       vb.customize ['modifyvm', :id, "--nicpromisc2", "allow-all"]
       vb.customize [
           "guestproperty", "set", :id,
           "/VirtualBox/GuestAdd/VBoxService/--timesync-set-threshold", 10000
          ]
    end
end
```

### Closing

It may be worth mentioning some good vagrant-like alternatives:

- [uvt-kvm](http://manpages.ubuntu.com/manpages/bionic/man1/uvt-kvm.1.html): Ubuntu virtualization front-end for libvirt and KVM
- [virt-builder](http://manpages.ubuntu.com/manpages/bionic/man1/virt-builder.1.html): Build virtual machine images quickly
- [virt-install](https://linux.die.net/man/1/virt-install): Provision new virtual machines
- [ansible-virt](https://docs.ansible.com/ansible/latest/modules/virt_module.html): Ansible virt module
- [Virt-Lightning](https://virt-lightning.org): Virt-Lightning: a CLI to start local Cloud image on libvirt
- ???: Please help me make this list better!

So, next time you find yourself installing vagrant-libvirt plugin, I hope this page can
make your life a little easier. Enjoy!


[Vagrant]: https://www.vagrantup.com/ "Vagrant Up"
[libvirt]: https://www.thegeekyway.com/kvm-vs-qemu-vs-libvirt/ "KVM vs QEMU vs Libvirt"
[vagrant-libvirt]: https://github.com/vagrant-libvirt/vagrant-libvirt "Vagrant Libvirt Provider"
[nesting]: https://searchvmware.techtarget.com/definition/nested-VM-nested-virtual-machine "nested virtual machine"
[nest1]: https://github.com/openstack-dev/devstack/blob/master/doc/source/guides/devstack-with-nested-kvm.rst "KVM-based Nested Virtualization"
[nest2]: https://www.server-world.info/en/note?os=Ubuntu_16.04&p=kvm&f=8 "Enable the setting for Nested KVM"
[nest3]: https://www.linuxtechi.com/enable-nested-virtualization-kvm-centos-7-rhel-7/ "How to enable Nested Virtualization in KVM on CentOS 7 / RHEL 7"
[disaster]: https://github.com/vagrant-libvirt/vagrant-libvirt/issues/770 "Vagrant libvirt plugin troubles"
[vagrantDownloads]: https://www.vagrantup.com/downloads.html "Vagrant Downloads"
[boxes]: https://app.vagrantup.com/boxes/search?provider=libvirt "Vagrant boxes for libvirt provider"
