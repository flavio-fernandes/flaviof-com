+++
author = "flaviof"
categories = ["hacks"]
date = "2026-08-03T19:00:00-04:00"
draft = false
tags = ["diy", "rpi", "linux", "c++"]
title = "office clock part 3"
+++

Ten years later, the office clock gets a new brain: Raspberry Pi OS Trixie, libgpiod and the kernel SPI subsystem. Not one wire moved.

<!--more-->

Back in 2016 I wrote up a clock I built into an Ikea cabinet. There were two
posts: [part 1][part1] covered the hardware and [part 2][part2] covered the
software. Those live on my old blog, so they will not show up in the sidebar
here -- go read them first if you want the whole story.

[![front panel](https://live.staticflickr.com/1640/26026460102_c277d6d820_h.jpg)](https://www.flickr.com/photos/38447095@N00/26026460102/ "Office Clock front panel")

That thing has been on my office wall ever since, quietly telling me the time
and dimming itself when the room gets dark. It never really broke. What broke,
slowly and without any drama, was everything *underneath* it: Raspbian Jessie
went end of life, the compiler got old, and [WiringPi][wiringpi] -- which I had
cloned from `git.drogon.net` and built by hand -- stopped being a thing you
could reasonably tell someone to install in 2026.

So this is part 3: same clock, same wires, brand new software stack.

### A ten-year-old clock still ticking

I built this out of an Ikea cabinet, four LED matrix panels, a 240-LED strip and
a Raspberry Pi Zero. Then I hung it on the wall and largely stopped thinking
about it, which is about the highest compliment you can pay a hobby project.

And it just kept working. That is genuinely the interesting part -- ten years of
telling the time, dimming itself at night, and doing a little animation when I
walk past. No corrupted SD card, no mystery lockups, no 3am reboots.

What rotted was underneath. Raspbian Jessie went end of life. The compiler got
old. And WiringPi -- which I installed back then by cloning
`git://git.drogon.net/wiringPi` and running `./build` -- stopped being something
you can reasonably ask anybody to do in 2026.

So the goal here was never "make the clock better." It was "make the clock
buildable again." Those are very different projects, and mixing them up is how
you end up with a broken clock and no idea which change did it.

### What aged and what did not

Nothing physical needed touching. Same four panels, same 240-LED strip, same
MCP3002 reading a photoresistor, same PIR motion sensor, same power supplies,
same breadboard, same wires. The HTTP interface and the animations behave the
way they always did.

Everything on the "aged" list is software, plus one piece of hardware I got to
delete:

- Raspbian Jessie becomes Raspberry Pi OS Lite Trixie
- gcc from 2014 becomes gcc 14.2
- WiringPi becomes libgpiod and the kernel's own SPI subsystem
- a powered USB hub and a wifi dongle become... nothing at all

Exhibit A, from the original build: a Pi Zero that needed a powered USB hub just
so it could hold a wifi dongle. The Zero W has the radio built in, so this entire
pile of plastic goes away.

[![rpi with hub](https://live.staticflickr.com/1611/25944285701_96c42d3b87_z.jpg)](https://www.flickr.com/photos/38447095@N00/25944285701/ "The original Pi Zero with its USB hub and wifi dongle")

That is my favorite line item in the whole project, because modernizing usually
means adding things. :)

### Same wiring, new brain

I gave myself one rule at the start: **not a single wire moves.**

This is the wiring from 2016, and it is also the wiring from today. Every pin in
this photo is still doing the same job for the same device.

[![gpio hookup](https://live.staticflickr.com/1551/25736053010_ec17090a03_c.jpg)](https://www.flickr.com/photos/38447095@N00/25736053010/ "GPIO hookup -- unchanged since 2016")

That sounds like sentimentality, but it is really about keeping the problem
small. If nothing physical changes, then every failure is a software failure,
and software failures are the kind you can undo at 11pm without a soldering
iron. It also meant I did the work on a *second* Pi Zero W, so the clock on the
wall kept working the whole time I was breaking things.

The nice part is that the rule ended up being enforced rather than remembered.
`make test-spi-overlay` pins all six BCM GPIO numbers in the merged Device Tree,
so if someone -- me, six months from now -- tidies up a pin number, it fails on a
laptop instead of on a clock that stops lighting up.

### Building a seam around the hardware

The first real change had nothing to do with libgpiod. It was putting a small
`Gpio` interface between the application and whatever happens to be driving the
pins, with the old WiringPi backend, the new one, and a **fake** one behind it.

The fake is the whole point. With it, the protocol tests run on a laptop, with
no Pi and no hardware, and they check the actual bit patterns the display
expects. That turns "does the clock still work?" from a question you answer by
squinting at a wall into one you answer in about a second at your desk.

Two build targets came out of this that I would recommend to anyone doing
something similar:

- **`make gpio-boundary`** is a grep over the sources for direct WiringPi calls
  outside the one legacy file. It means "the application no longer talks to
  WiringPi" is enforced by a test instead of by my good intentions, which is
  roughly the difference between a migration and a plan.
- **`make check-arm-warnings`** compiles everything with `-funsigned-char` and
  warnings as errors. Plain `char` is signed on x86-64 and unsigned on ARM, so
  your laptop will happily compile a signedness bug that only ever misbehaves on
  the Pi. If you cross-develop for a Pi and take one thing from this post, maybe
  take this one.

### Choosing the Linux subsystem that fits each device

My first instinct was to swap WiringPi for libgpiod everywhere and declare
victory. That worked, and it was far too slow.

The arithmetic explains why. One full strip frame is 240 pixels x 3 bytes x 8
bits = **5,760 data bits**, and more than 11,000 clock edges once you count both
sides of every bit. Pushing that through a character device -- with a lock, a
virtual call, a pin lookup and an ioctl on every single edge -- is an enormous
amount of ceremony to wiggle a wire. I added an mmap fast path, which helped and
still was not enough: CPU went from 3.55% on the old build to 9.14%, and the
strip still stuttered.

That failure is what produced the actual answer, which was to stop asking "which
GPIO library?" and start asking **"which kernel subsystem does each device
actually want?"** They turn out to want different things:

| Device | What it uses now |
| --- | --- |
| PIR motion sensor | libgpiod, an ordinary input |
| LED strip | kernel `spi-gpio` plus `spidev`, at 2 MHz |
| MCP3002 light sensor | kernel `spi-gpio` plus the native `mcp320x` driver |
| LED matrix | a narrow bulk write path of its own |

The strip and the ADC are byte-oriented devices, so they get SPI. Not the Pi's
*hardware* SPI, which lives on fixed pins and would have meant rewiring --
`spi-gpio`, a kernel software SPI controller that works on whatever pins you
tell it about. That is the piece that let the wiring rule survive. One write
submits a whole frame instead of thousands of individual GPIO calls.

The ADC does even better: it needs no transport code from me at all. The
kernel's own `mcp320x` driver claims the chip and hands back two files to read.

The matrix keeps a path of its own, because it deserves one. It has a
panel-select shift chain and command/data fields of 3, 7 and 4 bits, which does
not fold neatly into tidy byte-sized transactions. Forcing it through a shared
abstraction would have been worse than admitting it is special. Its bulk path
resolves the four pins to register masks once, then stores straight to the
registers -- 19.2 ms per full rewrite became 4.1 ms.

#### The best surprise in the whole project

At 1 MHz, the strip missed its 12 ms budget on **25 frames out of 25**, median
20.5 ms. Hopeless.

I raised the requested speed to 2 MHz. Same code, same wires, same overlay, one
constant changed. Median frame time: **3.0 ms**, and 25 out of 25 inside budget.
Twice the clock rate, nearly *seven times* less time.

That is not electrical, and no amount of staring at my own code would have found
it. `spi-gpio` calls a nanosecond delay helper on both sides of every clock edge
whenever the requested half-cycle is 500 ns or longer -- which is exactly 1 MHz
-- and that helper frequently rounds up to a whole microsecond. By asking for
*more* speed, I got the driver to stop waiting around.

Asking for more made it do less. I still smile at that one. :)

One honest footnote, since it would be easy to oversell: kernel `spi-gpio` is
still bit-banging. It is better scheduled than doing it from userspace, but it
is CPU work, not a hardware engine with DMA doing it for free. Fixing the
latency did not make the work disappear.

### Installing it in 2026

Part 2 had an installation section, so this one gets one too. My goal here is
that you can start with a brand new Pi Zero W and a brand new microSD card,
follow along top to bottom, and end up with a clock on a wall. If a step here
does not work for you, that is a bug on this page and I would like to hear
about it.

One decision I made up front: anything that makes the box healthier goes *into*
the recipe, not into a "and later you should also..." paragraph at the bottom.
A clock hangs on a wall for years and nobody ever babysits it, so the boring
maintenance choices belong at install time, while you are already paying
attention.

#### What you need

- A Raspberry Pi Zero W. Mine is a Rev 1.1.
- A new microSD card.
- The clock hardware from [part 1][part1]. Same panels, same strip, same
  sensors, same breadboard, same wires.

#### Burning the card

In 2016 I wrote the image with `dd` and then went digging through
`/etc/wpa_supplicant/wpa_supplicant.conf` to get wifi going, followed by
`ifdown wlan0` and `ifup wlan0`. Please do not do that anymore.
[Raspberry Pi Imager][imager] handles all of it before the card ever boots.

Choose **Raspberry Pi OS Lite (32-bit)**. Lite because there is no monitor on
this thing, and 32-bit because the Zero W is ARMv6 and the 64-bit images simply
will not boot on it. Then open the settings pane in Imager and fill in:

- hostname
- your username and password
- your wifi SSID and password
- your ssh public key

That last one matters more than it looks. It is the difference between a
headless box you can log into and a headless box you get to re-flash. :)

For the record, I am on Raspbian 13 (Trixie), kernel 6.18, gcc 14.2. Those are
the versions I tested, not the only ones that could possibly work.

#### First boot: stop the things that keep writing to your card

The clock's main process uses about 5 MB of memory. Almost everything else
touching that SD card is doing it for no reason, and flash wears out. Two
offenders, both of them defaults.

First, **cloud-init**. It is on the image so that Imager's first-boot settings
get applied. Once that has happened, it has nothing left to do, yet it wakes up
on every single boot and writes to `/var/lib/cloud` plus a couple of log files
forever. Once you are logged in and happy, show it the door:

```
sudo apt purge -y cloud-init
sudo rm -rf /var/lib/cloud /var/log/cloud-init.log /var/log/cloud-init-output.log
```

If you would rather keep the package around, `sudo touch /etc/cloud/cloud-init.disabled`
is the gentler version of the same idea.

Second, **swap**. Swap on this image is zram, which is a compressed block device
living in RAM. That part is good and worth keeping. The problem is what Raspberry
Pi OS bolts onto it: a 446 MB `/var/swap` file on the card, attached through a
loop device, that zram periodically flushes cold pages into. A RAM-only swap
quietly becomes a recurring SD card writer.

The goal is to keep zram and remove the file entirely. Two pieces are needed,
and the second one is the one that actually makes it stick.

First, stop the generator that builds the whole loop-and-file arrangement at
boot:

```
sudo mkdir -p /etc/systemd/system-generators && \
sudo ln -sf /dev/null /etc/systemd/system-generators/rpi-swap-generator
```

`rpi-swap-generator` does not just write a config file. It also emits systemd
unit drop-ins that wire `/var/swap` in as a hard dependency of the zram setup,
which is why nothing short of masking the generator keeps the file from coming
back on the next boot.

Second, define zram yourself, since you just removed the thing that was doing it:

```
sudo mkdir -p /etc/systemd/zram-generator.conf.d
sudo tee /etc/systemd/zram-generator.conf.d/20-rpi-swap-zram0-ctrl.conf > /dev/null <<'EOF'
[zram0]
host-memory-limit=none
fs-type=swap
zram-size=426
EOF
```

`zram-size` is in MB and should match your board's RAM -- 426 is what a 512 MB
Pi Zero W works out to. If you want to see what the generator would have chosen
before you mask it, `systemd-analyze cat-config systemd/zram-generator.conf`
prints the effective configuration, drop-ins and all.

Then reboot and confirm:

```
cat /sys/block/zram0/backing_dev
sudo swapon --show
df -h /
```

`backing_dev` should read `none`, meaning zram has nowhere on the card to write
even if something asks it to. `sudo swapon --show` should still list
`/dev/zram0` at 426 MB, because you kept the swap.

**Reboot first, and do not skip it.** Run that same `cat` before rebooting and
it still says `/dev/loop0`, because the loop device from this boot is already
attached and masking a generator does nothing to a machine that has already
started. That reading is not a sign the fix failed; it is a sign you have not
rebooted yet. I have watched myself misread it.

The `sudo` on the middle command is not decoration either -- `swapon` lives in
`/sbin`, which is not on a normal user's `PATH`, so without it you get
`swapon: command not found` and briefly think something is broken.

What `df` shows depends on where you started, and this surprised me:

- On a **fresh install**, following this page from the top, `df` does not move at
  all. That is the correct outcome. You masked the generator before the swapfile
  ever grew to full size, so there is nothing to reclaim -- you simply never pay
  the 446 MB in the first place.
- On a **box that has been running a while**, that file is already there at full
  size, and removing it is where the **446 MB** actually comes back.

So if you came here to shrink an existing card, expect a big number. If you are
building from scratch, expect nothing to happen, and count that as success.

For the second case: if `/var/swap` is still sitting there, delete it *after*
the reboot -- with the generator masked, nothing will bring it back. One warning
though: deleting it while a loop device still holds it open frees nothing at all.
`df` will not move until the last holder lets go, so reboot first and delete
second, in that order.

I did think about disabling swap entirely, and I am glad I did not. On an
overnight run this box had 53 MB sitting in swap against 217 MB resident across
*everything running on it* -- that is the whole system, not the clock. The clock
itself is about 5 MB. Under zram those 53 MB are compressed pages in RAM, not
writes to the card. Turn swap off and they just become uncompressed again, for
no benefit at all.

Names vary by image -- mine is `rpi-swap-generator` with `/var/swap`, and
`man rpi-swap` documents the Raspberry Pi side of it.


#### Packages

Short list, and everything on it is actually needed:

```
sudo apt update
sudo apt install -y git build-essential pkg-config libevent-dev \
    libmosquitto-dev libgpiod-dev gpiod
```

Yes, `git` is on that list. The Lite image does not ship it, which catches me
out roughly every single time.

`gpiod` is on it for a different reason. `libgpiod-dev` gives you the headers
the build needs, but it ships no programs at all -- the command line tools
`gpiodetect`, `gpioinfo` and friends live in the separate `gpiod` package. You
do not need them to build or run the clock, but you very much want them the
first time something does not light up, and the verification steps below use
`gpiodetect`.

Compare that to 2016, when it was `git libevent-dev` plus a manual WiringPi
build out of `/usr/local`. The build also links `libatomic` on ARMv6, but that
one ships with gcc so there is nothing to install. `device-tree-compiler` and
`raspi-utils-dt` give you `dtc` and `dtoverlay`, and both are already on the Lite
image.

#### Getting the code

```
git clone -b rpi-2.0.y https://github.com/flavio-fernandes/oclock.git \
    /home/pi/oclock.git
```

Two things worth saying about that command.

Clone **`rpi-2.0.y`**, not `master`. It is the same idea as the `rpi-0.1.y`
branch part 2 pointed at: a branch that matches what this article describes and
that can still take bug fixes, while `master` is free to move on. If you ever
need the exact bits I measured, the [`v2.0.0`][v200] tag is the one to use.

And clone it into **`/home/pi/oclock.git`** specifically. The systemd units below
have that path baked into them. If your user is not `pi`, either adjust the path
in `misc/oclock.service` and `misc/oclock-strip-spi.service`, or accept a
symlink. I would rather tell you that than have you find out from a service that
refuses to start.

#### Building

```
cd /home/pi/oclock.git && \
make
```

That is the whole thing. Plain `make` builds the Zero W profile. If you like
poking at build targets, they are all written up in
[docs/development.md][devdocs] and a few of them are genuinely interesting.

#### The Device Tree overlay

Here is the step that has no 2016 equivalent at all.

The LED strip and the ADC are now driven through the kernel's SPI subsystem
instead of by bit-banging every edge from userspace. But they are wired to
arbitrary GPIOs, not to the Pi's hardware SPI pins, and I promised myself I
would not move a single wire. The way out is `spi-gpio`: a kernel driver that
turns *any* pins into an SPI controller. It just needs to be told about them,
which is what the overlay does.

```
cd /home/pi/oclock.git && \
make spi-overlay && \
sudo cp build/oclock-spi-overlay.dtbo /boot/firmware/overlays/oclock-spi.dtbo
```

Look carefully at that last line, because the file gets **renamed** on the way
in. The build produces `oclock-spi-overlay.dtbo`, but the boot config line says
`dtoverlay=oclock-spi`, and that looks for `oclock-spi.dtbo`. Get it wrong and
nothing complains -- you just reboot into a Pi where the overlay silently did
not load. Ask me how I know. :)

Now the one line of boot config, with a backup first, because this is the file
that can cost you a boot:

```
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak && \
echo 'dtoverlay=oclock-spi' | sudo tee -a /boot/firmware/config.txt && \
sudo reboot
```

If that ever leaves you with a Pi that will not come up, do not panic. Power it
off, pull the card, put it in any other computer, and edit `config.txt` on the
small boot partition -- it is plain text and it mounts anywhere. Delete the line
you added, or copy `config.txt.bak` back over it.

The repo also has [`misc/managePhase5SpiOverlay.sh`][overlaysh], which is what I
actually used. It checksums the overlay, keeps a timestamped byte-for-byte
backup of `config.txt`, refuses to run if the clock is still running, and
deliberately does not reboot for you. It is stricter than the two commands above
-- it checks the board model and revision -- so I would reach for the plain
version first and read the script if you want the paranoid one.

After the reboot, you should see two new SPI controllers, and the ADC should
already be alive:

```
ls /sys/bus/spi/devices/
ls /sys/bus/iio/devices/
gpiodetect
```

#### Nothing at all for the ADC

I want to call this out because it is the happy case, and because the contrast
is the best lesson in the whole project.

The MCP3002 needs no setup step. None. The kernel already has an `mcp320x`
driver, the overlay describes the chip as `microchip,mcp3002`, and the kernel
takes one look and adopts it. It shows up under `/sys/bus/iio/devices/` as a
couple of raw channels and you just read them.

The LED strip gets no such welcome, which is the next section. Two devices, same
bus, same overlay -- one of them the kernel claims on sight, the other needs to
be introduced by hand. That difference is exactly what "use a proper kernel
subsystem" does and does not buy you.

#### The two services

The strip's overlay entry uses a compatible string that belongs to this project,
which means no in-tree driver claims it, which means `/dev/spidev*` does not
exist until something explicitly binds it. That is what
`oclock-strip-spi.service` is for. It runs once at boot, does the binding, and
`oclock.service` depends on it.

```
cd /home/pi/oclock.git && \
sudo cp misc/oclock.service misc/oclock-strip-spi.service /etc/systemd/system/ && \
sudo systemctl daemon-reload && \
sudo systemctl enable --now oclock-strip-spi.service oclock.service
```

`/etc/systemd/system` is where locally installed units belong. In 2016 I copied
the unit into `/lib/systemd/system` instead, which is really the package
manager's territory, and it worked fine for a decade -- but there is no reason
to repeat it now that I am typing the instructions out fresh.

The dependency is `Requires=`, not `Wants=`, and that was on purpose. Without
the binding there is no device to open, the clock fails to start its SPI output,
and `Restart=on-failure` would happily turn that into a crash loop that looks
like a hardware fault. With `Requires=`, the clock just refuses to start and
tells you why. A service that stays down is much easier to debug than one that
restarts forever.

Then check your work:

```
systemctl status oclock-strip-spi.service oclock.service
ls -l /dev/spidev*
```

At this point the clock should be lit. If it is, the rest of this section is
about keeping it that way.

#### The log file, which turns out to be the busiest writer of all

Remember the whole "stop the things that write to your card" theme? I saved the
worst one for after the clock is running, because you need the service installed
before you can fix it.

`oclock` embeds a small web server called pulsar, and pulsar keeps a log. By
default it lands in `log/pulsar.log` next to the binary, at the chattiest
verbosity there is. That alone would be fine. What makes it interesting is the
logging function itself, which does this for **every single line**:

```
write(log->fd, line, line_sz);
fsync(log->fd);
```

An `fsync` per log line. That is not buffered, not batched, not rotated -- it is
"go bother the flash chip right now," over and over, for as long as the clock is
plugged in. And nothing ever truncates the file, so it also grows forever.

Happily there is already a `-l` flag to point that log somewhere else. Add it
with a drop-in rather than editing the unit:

```
sudo mkdir -p /etc/systemd/system/oclock.service.d
sudo tee /etc/systemd/system/oclock.service.d/10-nolog.conf > /dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/home/pi/oclock.git/oclock -l /dev/null
EOF
sudo systemctl daemon-reload
sudo systemctl restart oclock.service
```

The empty `ExecStart=` on its own line is not a typo and you cannot leave it
out. `ExecStart` is a list that a drop-in would otherwise *append* to, so
without the reset systemd sees two commands and refuses to start the unit.
Clearing it first, then setting the real one, is the idiom.

The reason to prefer this over a quick `sed` on the unit file is that the unit
came out of the repo. Edit it in place and the change is invisible in `git`, and
the day you re-copy `misc/oclock.service` after an update -- which the deploy
steps below tell you to do -- it silently reverts and your card starts getting
hammered again with nothing to indicate why. The drop-in survives that, and
`systemctl cat oclock` shows you both pieces stacked in order.

`/dev/null` accepts the writes and forgets them. The `fsync` that follows each
one actually fails on a character device -- it returns `EINVAL` -- but the
logger discards that return value, so nothing notices and nothing touches the
card. If you would rather keep some logging, `-v 0` turns the verbosity down
instead of throwing the log away, and you can combine the two.

I want to be clear that this is worth doing **whether or not** you go read-only
below. A per-line `fsync` to a microSD card, forever, on a box that just displays
the time, is the single most pointless bit of wear on the whole system.

#### Cap the journal

Everything a service prints goes to the systemd journal, and the journal will
happily grow. Put a ceiling on it:

```
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/10-oclock-cap.conf > /dev/null <<'EOF'
[Journal]
SystemMaxUse=32M
RuntimeMaxUse=16M
EOF
sudo systemctl restart systemd-journald
```

Both keys are there on purpose: `SystemMaxUse` bounds a journal stored on disk,
`RuntimeMaxUse` bounds one stored in RAM, and which one applies depends on a
setting you have not necessarily seen. Setting both means you are covered either
way. Check what you actually got with:

```
systemd-analyze cat-config systemd/journald.conf
```

Use that command rather than reading `/etc/systemd/journald.conf` or grepping
for the setting -- it is the only thing that accounts for drop-in precedence,
and the shortcuts get it wrong in both directions. There is a longer story about
that in the [gotchas post][gotchas].

#### Trimming what a clock does not need

Do this now, while the root filesystem is still writable. The next section takes
that away.

In 2016 I disabled avahi and ripped out bluetooth. That advice has aged badly:
half the packages I named back then are not on the Lite image at all anymore.
What is still there is a different set of things, and going through it properly
turned up a nice surprise -- **more than half the enabled units on a stock image
do nothing whatsoever for a clock.**

First, packages that can just leave. Which of these you actually have depends on
how old your image is, so purge them one at a time and let the missing ones go
by:

```
for p in avahi-daemon bluez udisks2 rpi-eeprom-update; do
    sudo apt-get purge -y "$p" || echo "not present, skipping: $p"
done
sudo apt autoremove --purge -y
```

That loop is not me being fussy. Hand `apt` a name it has never heard of and it
does not skip that one and carry on -- it stops with
`Error: Unable to locate package` and removes **nothing at all**. So the obvious
one-liner would quietly do nothing on an image that never shipped
`rpi-eeprom-update`, and you would not find out until you wondered why the card
was still full. Sticking `|| true` on the end of the one-liner is worse, not
better: it hides the error and still removes nothing.

Note there are two different situations here, and only one of them is a problem.
A package that exists but is not installed is fine -- apt says "not installed,
so not removed" and exits happily. It is only a name apt cannot find at all that
poisons the whole command.

Then a couple of these deserve a word.

**avahi** is the one with a consequence: removing it kills mDNS, so
`oclock.local` stops resolving. In 2016 I did not care; if that is how you reach
your box, you will. Purge rather than disable, by the way -- `avahi-daemon.socket`
will cheerfully restart the daemon you just stopped.

**`rpi-eeprom-update` is a Pi 4 and Pi 5 tool** -- it updates a bootloader
EEPROM that the BCM2835 in a Zero W simply does not have. On a current Lite
image it is not installed on this board at all, which is the correct outcome and
the reason the loop above shrugs it off. Older images did ship it, so it is in
the list for anyone starting from one of those.

`udisks2` is in the same category: it is there to automount removable media for
a desktop session, nothing on a headless clock ever calls it, and current Lite
images do not include it either. When it *is* present it brings the whole
`libblockdev` family with it, which is most of what `autoremove` sweeps up
afterwards.

The `autoremove` at the end is where the real weight comes off. On my build it
followed the dependencies and took **55 further packages** with it -- the
`libblockdev` set, a pile of Python that came in with cloud-init, and the avahi
libraries. Nothing on that list is anything a clock has ever called.

Next, the timers. Every one of these exists to write something:

```
sudo systemctl mask apt-daily.timer apt-daily-upgrade.timer \
    dpkg-db-backup.timer man-db.timer logrotate.timer \
    e2scrub_all.timer fstrim.timer
```

Under a read-only root these matter for a slightly different reason than usual.
It is not that they wear out the card -- they cannot, the card is read-only.
It is that their writes land in the RAM layer instead, which is the thing you
are trying to keep small. A daily `man-db` rebuild is harmless on a laptop and
is pure overlay consumption here.

Two of them are outright nonsense on this box: `e2scrub_all` scrubs a filesystem
that is mounted read-only, and `fstrim` sends TRIM to it. Neither has anything
to do.

Finally, the first-boot leftovers -- things that did their job once, on the very
first power-on, and stayed enabled anyway:

```
sudo systemctl disable regenerate_ssh_host_keys.service sshswitch.service \
    systemd-pstore.service keyboard-setup.service console-setup.service
```

Just as important is the list I deliberately **did not** touch: NetworkManager
and `wpa_supplicant` (that is the wifi), `systemd-timesyncd` (no real-time clock
on a Pi, and this is a clock, so this one is load-bearing), `ssh`, `oclock`,
`oclock-strip-spi`, `mqtt2cmd`, and the systemd furniture -- dbus, journald,
logind, udevd. I also kept `getty@tty1`, because if I ever break the network I
would like to be able to plug in a keyboard.

Here is what all of that bought:

| | Before | After |
| --- | ---: | ---: |
| Boot time | 1 min 48.9 s | 1 min 41.0 s |
| Enabled units | 33 | 17 |
| Running services | 15 | 14 |
| Card used | 40% | 38% |
| Memory available | 240 MB | 250 MB |

Eight seconds. I want to be honest about that rather than dress it up -- if you
came here for a fast boot, this is not the section that delivers it, and the
[gotchas post][gotchas] has the measurement of where the boot time actually
goes.

The number I find interesting is the second row. Thirty-three enabled units down
to seventeen, and the clock does not notice. That is not a tuning win, it is a
statement about how much of a general-purpose OS image is aimed at a use case
you do not have.

#### Read-only root

Same logic as the swap section, taken as far as it goes: if the card is never
written to, it cannot wear out. Raspberry Pi OS ships an overlay filesystem mode
for exactly this. Turn it on and the root filesystem becomes read-only, with all
writes going to a RAM layer stacked on top that is thrown away at every reboot.

This is running on my clock now, through a dozen-odd reboots and three pulled
power cords.

One thing first, while you still can. Add this drop-in **before** you turn the
overlay on:

```
sudo mkdir -p /etc/systemd/system/systemd-remount-fs.service.d
sudo tee /etc/systemd/system/systemd-remount-fs.service.d/10-overlayroot.conf >/dev/null <<'EOF'
[Unit]
ConditionKernelCommandLine=!overlayroot
EOF
```

The order genuinely matters, and it is the first place this whole scheme will
bite you. The moment you reboot into the overlay, `/etc` is read-only -- so if
you write that file afterwards it goes into the RAM layer, works perfectly until
you reboot, and then is simply gone. You would be left wondering why a fix you
know you applied did not stick. From here on, anything that has to survive a
reboot has to be written while the card is still writable.

Without the drop-in, `systemd-remount-fs.service` fails on every single boot
under the overlay. That sounds cosmetic and is not -- on my clock it cascaded
through a `Requires=` edge and left the box with no swap at all, silently. The
[gotchas post][gotchas] has the full account. A condition rather than a mask,
because this way the same file is correct whether the overlay is on or off, and
you never have to think about it again.

Now turn it on:

```
sudo raspi-config nonint enable_overlayfs
sudo reboot
```

To check which state you are in:

```
sudo raspi-config nonint get_overlay_now     # is it active right now?
sudo raspi-config nonint get_overlay_conf    # will it be after a reboot?
```

Both print a shell exit status rather than a word, so brace yourself: **`0`
means yes, `1` means no.** If the two disagree, you have changed the setting and
not rebooted yet. Note the kernel parameter these toggle is `overlayroot=tmpfs`,
not the `boot=overlay` you will see in a lot of writing about read-only Pis --
grep for the wrong one and you will conclude the overlay is off while it is on.

#### Deploying once it is read-only

`/home/pi` is ephemeral now, which is where `oclock` lives. Reading works fine;
it is *writes* that vanish at reboot.

You do not have to reboot to see this, and looking directly at it is a better
way to understand the overlay than taking my word for it. Both layers are
mounted and browsable while the thing is running:

```
touch /home/pi/PROOF.txt
ls -l /home/pi/PROOF.txt                        # there
ls -l /media/root-rw/overlay/home/pi/PROOF.txt  # there too -- this is RAM
ls -l /media/root-ro/home/pi/PROOF.txt          # not there -- this is the card
```

The file is visible normally, it exists in the RAM upper layer, and it is simply
absent from the card underneath. That third line is the whole read-only story in
one command. And everything you would do to update the clock -- `git pull`,
`make`, editing a config -- puts its results in exactly the same place as
`PROOF.txt`.

So updating stops being `git pull && make` and becomes:

```
sudo raspi-config nonint disable_overlayfs
sudo reboot
```

then, once it is back:

```
sudo raspi-config nonint get_overlay_now      # want: 1
cd /home/pi/oclock.git && git pull && make
sudo systemctl restart oclock.service
```

and when you are happy:

```
sudo raspi-config nonint enable_overlayfs
sudo reboot
```

Two reboots to deploy. That is the honest price, and for a box I touch a couple
of times a year it is worth it. If you update yours weekly it may well not be,
and leaving the root filesystem writable is a perfectly respectable answer.

I have run that whole cycle for real rather than rehearsing it -- overlay off,
reboot, confirm the filesystem is genuinely writable, do the service trimming
above and bring the checkout up to the release tag, overlay back on, reboot --
checking `get_overlay_now` at every step. It is tedious and it works. Checking
at every step is not paranoia, either -- the [gotchas post][gotchas] has the
story of the time one of those reboots quietly did not happen and I spent a
while blaming the overlay for it.

Finally, watch the RAM layer rather than trusting it. It only ever fills up
while the box is running:

```
df -h /
```

Mine sits at 160 KB of 214 MB. Steady climb means a writer you have not found
yet.

### What ten years changed in the application

Part 2 ended with a "future enhancements" list, the way these posts always do.
MQTT was on it. Ten years is a long time to leave a TODO lying around, but it is
real now: the clock publishes light level, motion, display intensity and display
mode over libmosquitto, so the rest of the house can see what it sees.

To be precise, because it would be easy to overclaim: it **publishes** but does
not **subscribe**. There is no MQTT control topic. The HTTP interface is still
how you tell the clock what to do.

Beyond that, the application a user sees is deliberately the same. Same display
modes, same animations, same web endpoints. What changed is underneath: it now
shuts down cleanly instead of being killed, and there is an actual test suite
where there used to be me squinting at a wall.

One target from that suite is worth singling out, `make valgrind`. The unit
tests already run under AddressSanitizer and UBSan, but those cover pieces in
isolation. `make valgrind` runs the *whole* application -- every thread, the
event loop, the MQTT client, the shutdown path -- under `--leak-check=full`,
which is where the interesting leaks actually live. It takes about three and a
half seconds. It sits outside `make test` only because it needs valgrind
installed, not because it is expensive, which makes "I'll run it later" a much
weaker excuse than it sounds.

### The dimming bug I explained wrong twice

Automatic dimming did not work on the new build. The obvious conclusion was that
I had broken it, and I spent a while believing that.

The one thing I did right was refusing to debug the transport and the
calibration at the same time. First I proved the ADC: read both MCP3002
channels, cover the sensor, uncover it, write the numbers down. The ADC was
perfectly fine.

So then I turned off the room light and stood there watching. In a dark room the
value settled between **355 and 478**. The threshold for "dark" was **360**. So
there it was: a constant that had been sitting above the darkest the room ever
got, unreachable, quietly broken since 2016 and never noticed.

Tidy story. I wrote it down. It was wrong.

What corrected it was not another look at the hardware. This clock has been
publishing its light reading to a public feed since 2020, and -- the part that
makes it worth anything -- what it publishes is exactly the ten-sample moving
average that the dimming logic compares. Not a proxy for the decision variable.
The decision variable itself, every few minutes, for years.

Sixty days of it, 15,884 samples:

{{< figure src="img/office-clock-part3/lux-dimming.png" title="" >}}

Read it from the bottom. The dark end of every day sits near 150 and does not
budge across the cutover. What moved is the top: a bright plateau that peaked at
**725** across 15,357 readings, never once above 750, becomes a flat **1022** for
about a third of all samples afterward. That is the 10-bit ceiling. The sensor
is now clipping.

Which means the room was reaching 360 all the time. **32.9%** of pre-migration
samples were below it. Replay the original 360/500 hysteresis across 57 days and
it produces 106 dim events and 105 bright ones -- roughly two transitions a day,
every day, right on schedule. The old constant was not unreachable. It had been
working the whole time.

My ten minutes in a dark room had been a real measurement of a real condition.
It just was not the darkest condition that room reaches, and there was no way to
know that from standing in it.

**The genuinely interesting finding** is what the change did to *separation*.
Split the history by hour of day:

| | night, 01-05h (p95) | day, 09-17h (p05) | gap |
| --- | ---: | ---: | ---: |
| Original software | 630 | 420 | **-210, overlapping** |
| New software | 408 | 615 | **+207, clean** |

Before the migration a bright night could read *higher* than a dull day. The two
conditions overlapped by 210 counts, so no threshold pair could have been
dependable -- and that, rather than a bad constant, is the real reason dimming
felt temperamental for a decade. Afterwards they are cleanly separated by about
200 counts. The clipping that looks like a regression is precisely what bought
that separation. It does ruin the feed as a light *measurement*, but for a
two-state dim-or-bright decision it costs nothing.

Why the top of the range moved, I genuinely do not know. A uniform scale factor
is ruled out, because the dark end did not move -- and the retired bit-bang is a
correct 10-bit read, which I checked. My best guess is that the old code sampled
the data line a little too soon after the clock edge, an error that would grow
with the number of set bits and so hit 1022 hard while barely touching 150. That
is a hypothesis, not a finding. The hardware that could settle it is retired, so
it stays one.

The thresholds are now **460 and 600**. 460 sits above the night p95 of 408 and
127 counts below the daytime minimum of 587. 600 replaced 700 because 700 was
*above* that daytime floor: on a naturally lit morning the clock held itself dim
until 09:52, where 600 lets it brighten at 07:24.

And then the very first unattended night settled it, without being asked to:

```
01:57 EDT  ->  DIM     (v=313)
06:33 EDT  ->  BRIGHT  (v=637)
```

Dimmed for four and a half hours, then woke at **637**. Look at that number
against the old high-water mark of 700 -- at 637 it never would have crossed it.
The clock would have sat there dimmed straight through the morning, which is
precisely the complaint that started this whole investigation. It reproduced
itself on the first night, unprompted, and the new threshold caught it.

The floor that night was 118 and the median 337, so getting *into* dark was
never the question. It never was. It was always coming back out.

There is a smaller and more embarrassing version of the same lesson in the same
project. My compatibility test suite had four assertions that inspected build
output through `make -n` -- and `make -n` prints nothing when the thing is
already built. Those assertions matched nothing and passed anyway. They only
ever "worked" because that target happened to run first in a clean tree. Running
the suite twice in a row is what exposed it, and I only did that by accident
while checking whether some *other* assertion could fail.

A test that passes for the wrong reason is worse than no test, because it also
spends your confidence.

### Measurements and final acceptance

Everything above is a story. Here are the numbers behind it. The application
ticks every 12 ms, so that is the budget everything else has to fit inside.

| What | Before | After |
| --- | --- | --- |
| Strip frame, 240 pixels | 20.5 ms median at 1 MHz, 0 of 25 in budget | **3.0 ms median at 2 MHz, 25 of 25** |
| Matrix full rewrite | 19.2 ms per-edge, 0 of 20 in budget | **4.1 ms burst, 20 of 20** |
| CPU, mmap experiment vs original | 3.55% | 9.14% (this is why that approach lost) |
| Night/day separation | -210 counts, the bands overlapped | **+207 counts, cleanly apart** |
| Dimming thresholds | 360 / 500 | 460 / 600 |

And the boot, which is its own kind of measurement:

| Stage | Time |
| --- | --- |
| Full boot | 2 min 24.8 s |
| of which NetworkManager | 59.6 s |
| of which cloud-init | 21.6 s |
| Strip binding service | 4.96 s |

That cloud-init line is the one that sent me off removing it during the install
-- 21 seconds every boot, for a thing whose entire job finished the first time
the Pi ever powered on.

With cloud-init gone and the services trimmed, the boot is down to **1 min
41 s**. Almost all of what remains is a single service, and I measured that one
carefully enough that it got [its own section in the gotchas post][gotchas].

For unattended behavior: the first measured soak, before any of the read-only
work, ran **8 h 53 min** with zero restarts, zero warnings and no wifi drops.
It also comes back on its own after a reboot -- binds its own SPI device, starts
its own service, no human involved.

And running read-only, after the three fixes above:

| Metric | Value |
| --- | --- |
| Writable RAM layer | 160 KB of 214 MB |
| Swap | 426 MB zram, `backing_dev: none` |
| Card reclaimed | 446 MB (3.0 G to 2.6 G, 46% to 40%) |
| Card used after trimming | 38% |
| `oclock` RSS | 5,300 KB, unchanged throughout |
| Service restarts | 0 |
| Failed units | 0 |
| Read-only violations | 0 |

The RSS line is the one I like. Every single thing on this page -- the transport
rewrite, the kernel SPI move, the read-only root, all of it -- and the process
sits at the same 5 MB it always did.

Over eight hours of hourly sampling the writable RAM layer oscillated between 64
and 124 KB with no upward trend, memory available stayed flat, and nothing
restarted. It has been through a dozen-odd reboots since -- clean ones, deploy
cycles and three pulled power cords -- and it comes back to the same place every
time. That is hours and a lot of power cycles, not days. I am not going to claim
a week I have not watched.

#### And then I pulled the plug

Three times, at the wall, about ten seconds off, no shutdown command, nothing
warned in advance. This is the test the whole read-only exercise was for, so it
seemed only fair to actually do it.

**It passed three out of three.** Every time: the config and scripts on the card
matched their pre-cut checksums, the `oclock` binary matched, both boot files
matched, every service came up active with zero restarts, the strip bound its
SPI device, and the display came back correct -- which I checked with my eyes,
not a script.

The detail I like best is the ext4 mount count. It stayed at **15** across all
three cuts. A read-only mount does not increment it, so that number is direct
evidence the card was genuinely never written to, rather than written to
carefully.

And one line in the kernel log that says the whole thing better than this
section does:

```
EXT4-fs (mmcblk0p2): orphan cleanup on readonly fs
```

The unclean cut left orphan inodes behind. ext4 noticed them, and then declined
to clean them up, because the filesystem is read-only. It would not write even
to heal itself. That is not a failure -- that is precisely the property I was
after, caught in the act.

One quirk the cuts made obvious: the Pi has no real-time clock, and under the
overlay the file systemd uses to guess the time is frozen at the moment the
overlay was enabled. So each of those three boots came up believing it was
mid-afternoon on the day I turned it on, until NTP corrected it a few seconds
later. Harmless in practice, and [worth understanding][gotchas] if you are going
to run one of these.

### Thanks

Big thanks to **Codex** and **Claude** for the assist on this one. A lot of this
migration was long, fiddly, measure-it-again work -- Device Tree overlays, SPI
timing, chasing a dimming bug that turned out to be a decade-old constant -- and
having a tireless pair to think out loud with made it genuinely fun instead of a
chore. They also helped me put this page together.

And thanks to you for reading this far. If something here was not well
described, don't be shy about reaching out. There are more photos of the build
in the [Flickr album][flickr] if you want to see how the sausage was made.

Go makers go! :)

Enjoy!

{{< copy-buttons >}}

<style>
/* The 2016 theme collapses table borders but never draws any, so tables read
   as floating columns. Scoped here rather than touching the vendored theme. */
.post table {
    border-collapse: collapse;
    margin: 1.5rem 0;
    width: 100%;
    font-size: 0.95rem;
}
.post table th,
.post table td {
    border: 1px solid #ccc;
    padding: 0.5rem 0.75rem;
    text-align: left;
    vertical-align: top;
}
.post table th {
    background: #f2f2f2;
    font-weight: 700;
}
.post table tr:nth-child(even) td {
    background: #fafafa;
}
</style>

[gotchas]: post/hacks/readonly-rpi-gotchas/ "Read-only Raspberry Pi gotchas"
[part1]: https://flaviof.com/blog/hacks/office-clock-part1.html "Office Clock Project Part 1: Hardware"
[part2]: https://flaviof.com/blog/hacks/office-clock-part2.html "Office Clock Project Part 2: Software"
[v200]: https://github.com/flavio-fernandes/oclock/releases/tag/v2.0.0 "oclock v2.0.0"
[devdocs]: https://github.com/flavio-fernandes/oclock/blob/rpi-2.0.y/docs/development.md#make-targets "oclock make targets"
[overlaysh]: https://github.com/flavio-fernandes/oclock/blob/rpi-2.0.y/misc/managePhase5SpiOverlay.sh "Guarded overlay install helper"
[imager]: https://www.raspberrypi.com/software/ "Raspberry Pi Imager"
[wiringpi]: https://github.com/WiringPi/WiringPi "WiringPi"
[flickr]: https://flic.kr/s/aHskxgSqtB "Office Clock Project photos"
