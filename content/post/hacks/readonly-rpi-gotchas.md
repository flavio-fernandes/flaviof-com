+++
author = "flaviof"
categories = ["hacks"]
date = "2026-08-04T18:00:00-04:00"
draft = false
tags = ["diy", "rpi", "linux"]
title = "read-only raspberry pi gotchas"
+++

The things that broke when I made a Raspberry Pi read-only, and why none of them were where the error message pointed.

<!--more-->

The box here is a Raspberry Pi Zero W that has been running a clock on my office
wall since 2016 -- LED matrix panels, a 240-LED strip and a light sensor. In
2026 I rebuilt its software, and then made its root filesystem **read-only**, so
that the SD card is never written to and cannot wear out. Two service names show
up below: `oclock` is the clock itself, and `oclock-strip-spi` is a small unit
that runs first and binds the LED strip to the kernel's SPI driver, because
nothing claims that device automatically.

Everything below came out of doing that. None of it is really specific to a
clock -- if you are making any Pi read-only, I think you will meet most of these.

The install steps themselves live in [office clock part 3][part3], written to be
followed top to bottom without stopping to think. This post is the opposite: the
failures, the wrong turns, and the two or three things that genuinely surprised
me. Read it if something has gone sideways, or if you like watching someone else
step on rakes. :)

### The failed unit you will definitely hit

Turn the overlay on and `systemd-remount-fs.service` fails on every single boot:

```
mount: /: fsconfig() failed: overlay: No changes allowed in reconfigure.
```

You will hit this. It is not something I did wrong, and it is worth
understanding rather than papering over, because the reason is genuinely
surprising.

At boot, overlayroot **rewrites `/etc/fstab`** so the `/` entry describes the
overlay instead of the SD card. Go and look at it and you find this:

```
/media/root-ro/ / overlay lowerdir=/media/root-ro/,upperdir=…,workdir=… 0 1
```

`systemd-remount-fs` then does its ordinary job -- read fstab, apply those
options to the live mount -- and the kernel refuses, because you cannot
reconfigure an overlay in place. The unit is doing exactly what it is supposed
to, on a config file that describes something it is not allowed to touch.

The reassuring part: **the fstab on your card is untouched and completely
normal.** That rewrite only ever exists inside the RAM layer, which is why the
unit goes back to working the moment the overlay is off.

So the fix should be conditional, not a mask:

```
sudo mkdir -p /etc/systemd/system/systemd-remount-fs.service.d
sudo tee /etc/systemd/system/systemd-remount-fs.service.d/10-overlayroot.conf >/dev/null <<'EOF'
[Unit]
ConditionKernelCommandLine=!overlayroot
EOF
```

That says "skip this unit when the kernel was booted with overlayroot." A mask
would also silence it, but a mask is wrong in the other half of your life: every
time you disable the overlay to deploy, you would need to unmask it, and then
remember to mask it again. The condition is correct in **both** states and
survives the whole disable/enable dance without you thinking about it once.

With the overlay on, the unit reports `ConditionResult=no, Result=success` and
logs nothing at all. With it off, it runs and succeeds. Both confirmed.

### ...and the reason that failed unit actually mattered

I nearly left that as cosmetic. A skipped remount on a filesystem that is
deliberately read-only sounds like the definition of harmless.

Then I ran `free` and the swap column was **zero**. On a 426 MB box.

Nothing had announced this. No error mentioned swap. Here is the chain:

- `rpi-setup-loop@var-swap.service` carries `Requires=systemd-remount-fs.service`
- that unit was failing, so the loop setup failed
- `systemd-zram-setup@zram0.service` depends on the loop setup, so it failed too
- and the box came up with no swap whatsoever, quietly

A unit I had written off as noise had taken out swap entirely, three
dependency edges away, and the only symptom was a zero in a column nobody looks
at. That is the argument for chasing down a failed unit even when it looks
cosmetic: the thing reporting the failure is very often not the thing that has
the problem.

### The clock that would not start, twice

This one is not about the overlay at all -- it bit me in the same week, and the
lesson travels a lot further than this project.

For two boots in a row, the clock simply did not come up. The journal:

```
[38.6] Starting oclock-strip-spi.service...
[53.2] udevadm: Timed out while waiting for udev queue to empty
[53.3] error: udev did not settle after binding
[55.1] spi4.0: Process '.../i2cprobe' failed with exit code 1
[64.0] oclock-strip-spi.service: Failed with result 'exit-code'
```

Binding the strip to `spidev` makes udev run a Raspberry Pi probe helper,
`i2cprobe`, against the new device. That probe fails and takes tens of seconds
doing it. My binder called `udevadm settle` afterwards and treated a timeout as
fatal, so the binder rolled back and exited non-zero -- and because
`oclock.service` has `Requires=` on it, the whole clock stayed down.

The binding itself had worked perfectly every time.

Here is the transferable bit: **`udevadm settle` waits on the global udev
queue.** Not your device's events -- everybody's. Any unrelated slow or failing
probe anywhere on the system can make it time out, and a timeout tells you
nothing whatsoever about whether *your* device is ready. Wait for the end state
you actually need instead. In this case that is the `spidev` driver symlink plus
the character device, which is a thing you can poll for directly. `settle` is a
hint at best.

### Keeping an eye on the RAM layer

Since the whole scheme depends on writes staying bounded, it helps to be able to
look. Two commands cover it:

```
df -h /
findmnt -no SOURCE,FSTYPE,OPTIONS /
```

`df -h /` is the one to actually watch -- with the overlay active, the "size" it
reports is the RAM layer's cap and the "used" is how much of it you have spent
since boot. `findmnt` confirms you are really running on an overlay and shows
you the `lowerdir` and `upperdir` behind it.

If you want a number you can watch over time:

```
df -h / | awk 'NR==2 {print $5" of "$2" used since boot"}'
```

Remember that this only ever goes up while the box is running. Seeing it climb
slowly is normal. Seeing it climb steadily is a writer you have not found yet.

For reference, after all of the above my clock sits at **160 KB of 214 MB**.
During the eight hours I sampled it hourly it wandered between 64 and 124 KB
with no upward trend, memory available stayed flat, and `oclock` held at
5,300 KB RSS throughout. It has been rebooted a dozen-odd times since -- clean
reboots, deploy cycles and three pulled power cords -- and it still lands in the
same neighborhood each time, which is the property I actually care about.

Hours and a lot of power cycles, though, not days. I am not going to claim a
week I have not watched.

The one number that does climb is the journal: 2.5 MB to 7.5 MB over those eight
hours, roughly 0.6 MB an hour. That is fine, because it lives in `/run` and is
capped at 16 MB, so it rotates rather than eating the overlay. But it is a
useful reminder that "bounded" and "not growing" are different things, and only
the first one is what you actually need.

One thing **not** to use as your health check, which cost me some time:
`systemctl is-system-running` reports `degraded` on this box permanently, and it
is lying to you. Every short SSH session leaves behind a failed transient scope:

```
session-cN.scope: PID … vanished before we could move it to target cgroup
session-cN.scope: No PIDs left to attach to the scope's control group, refusing.
```

That is a logind race -- the command finishes before logind can move the process
into its cgroup -- and it is completely harmless. But it means any box you poll
over SSH will read as "degraded" forever, and my hourly monitoring script was
manufacturing one of these per sample. Watch the actual list instead, with
session scopes filtered out:

```
systemctl list-units --state=failed | grep -v 'session-c[0-9]*\.scope'
```

### The systemd journal, which is the other big writer

Everything a service prints to stdout or stderr goes to the systemd journal, and
the journal is happy to grow. Whether that costs you SD writes or RAM depends on
one setting, and you can see exactly what is in effect with:

```
systemd-analyze cat-config systemd/journald.conf
```

That prints the shipped defaults plus anything overriding them, which is much
more useful than reading `/etc/systemd/journald.conf` and guessing. The setting
that matters is `Storage=`, and there is good news at the bottom of that output
on a Raspberry Pi:

```
# /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf
[Journal]
Storage=volatile
```

Raspberry Pi OS already decided this for you. `volatile` means the journal lives
in `/run/log/journal`, which is a tmpfs, so **the journal never touches your SD
card at all** -- one less writer to worry about, for free, before you do
anything.

Do not try to work this out by looking for the journal directory, and do not try
to work it out by grepping `/etc`. Both fail, and I know because I did the
second one *after* writing this warning.

Setting up monitoring for the read-only soak, I grepped
`/etc/systemd/journald.conf*`, saw no `Storage=` line, concluded the journal was
writing persistently into the RAM layer, and calmly projected that it would fill
the 214 MB overlay in about nine days. All of that was wrong. The setting lives
in a **vendor** drop-in under `/usr/lib`, which my grep never looked at. The
journal was in `/run/log/journal` the whole time and already capped.

`/var/log/journal` exists on this image even though storage is volatile, so the
directory test reports the opposite of the truth too. Only
`systemd-analyze cat-config` accounts for drop-in precedence, which is the entire
reason to use it. Believe the tool, not the two shortcuts.

The flip side is that a volatile journal is spending RAM rather than card, which
matters much more once you go read-only. Check what it is costing you:

```
journalctl --disk-usage
```

Then put a cap on it. The tidy way is a drop-in rather than editing the main
file, because drop-ins survive package updates:

```
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/10-oclock-cap.conf > /dev/null <<'EOF'
[Journal]
SystemMaxUse=32M
RuntimeMaxUse=16M
EOF
sudo systemctl restart systemd-journald
```

The two knobs are not interchangeable, which trips people up:
`SystemMaxUse=` applies to the **persistent** journal in `/var/log/journal`, and
`RuntimeMaxUse=` applies to the **volatile** one in `/run/log/journal`. On this
image it is `RuntimeMaxUse` that is doing the work, since storage is volatile --
but setting both costs nothing and means you stay covered if that ever changes.
Confirm it took with `systemd-analyze cat-config systemd/journald.conf` again --
your drop-in should appear at the bottom, which is what makes it win.

With the writers bounded, here is what the overlay costs.

### The clock file freezes, and it is worse than "reset"

A couple of things under `/var/lib/systemd` -- the saved clock and the random
seed -- stop being maintained once the overlay is on. For the random seed that
is a shrug. For the clock file, on a device whose entire job is telling the
time, it deserves a closer look, and my first description of it was too
generous.

The Pi has no real-time clock. On boot it genuinely does not know what year it
is, so systemd reads `/var/lib/systemd/timesync/clock` and starts from whenever
that file says it last ran. Under the overlay, that file lives in the read-only
layer and is **frozen at the instant you enabled the overlay**. It can never
advance again.

So it is not that the clock resets to something a few seconds stale. Every boot
starts out believing it is that one frozen moment, and the gap between that and
reality grows by a day for every day the overlay stays on. Leave it up for six
months and the box boots thinking it is six months ago, until NTP corrects it.

In practice this is still fine -- `systemd-timesyncd` fixes it within seconds of
wifi associating, and that is the entire exposure. But "briefly wrong" and
"briefly wrong by an unbounded amount" are different claims, and on a clock the
second one is worth knowing before you are surprised by it.

```
timedatectl
timedatectl show-timesync --all | grep -i poll
```

### Tips for everything else on the box

None of this is really about the clock, but the office clock Pi is not running
only the clock, and I suspect yours will not either. These are the things I
wanted to know once I started caring about what writes to the card.

#### Where are a service's logs actually going?

Anything a service prints to stdout or stderr goes to the journal unless it says
otherwise, and most units say nothing. You can check any unit without guessing:

```
systemctl show mqtt2cmd.service -p StandardOutput -p StandardError
```

If a unit does not set them, you get `StandardOutput=journal` and
`StandardError=inherit` -- which means inherit from stdout, which means the
journal as well. So "the unit file doesn't mention logging" reliably means "it
is all going to the journal."

I have a second service on the clock called `mqtt2cmd`, and its unit is exactly
that shape -- `Type=simple`, an `ExecStart`, `Restart=on-failure`, and not a word
about output. So everything it prints lands in the journal, which is why
`journalctl --unit=mqtt2cmd --follow` is how I read it. There is no separate log
file to find, and nothing is rotating anything, because journald is doing all of
that already.

#### How much is any one service costing you?

`journalctl --disk-usage` gives the total, not the per-unit share. For a rough
per-service number:

```
journalctl -u mqtt2cmd --since today | wc -l
journalctl -u mqtt2cmd --since "1 hour ago" | wc -l
```

Lines per hour is usually all you need to spot the noisy one. And if a service
is stuck in a `Restart=on-failure` loop it will bury everything else, so it is
worth checking:

```
systemctl show mqtt2cmd.service -p NRestarts
```

What you cannot do on a stock Pi image is ask systemd how much **memory** a
service is using. The obvious command looks like it works and quietly tells you
nothing:

```
systemctl show mqtt2cmd.service -p MemoryCurrent
```

You get an empty value for every service on the box. The reason is
`cgroup_disable=memory` on the kernel command line -- the memory controller is
switched off, so the only cgroup controllers available are `cpu`, `io` and
`pids`. systemd is not broken and neither is the unit; the accounting simply is
not there to read.

Fall back to plain process RSS instead:

```
systemctl show mqtt2cmd.service -p MainPID
ps -o rss=,comm= -p "$(systemctl show -P MainPID mqtt2cmd.service)"
```

Less tidy, and it misses child processes, but it is a real number rather than a
blank one.

#### Capping one chatty service without capping everything

The global `SystemMaxUse=` / `RuntimeMaxUse=` from earlier put a ceiling on the
journal as a whole. If you would rather rate-limit a single service so it cannot
crowd out the others, systemd will do that per unit, and a drop-in is the clean
way to add it without touching the shipped unit file:

```
sudo mkdir -p /etc/systemd/system/mqtt2cmd.service.d
sudo tee /etc/systemd/system/mqtt2cmd.service.d/10-ratelimit.conf > /dev/null <<'EOF'
[Service]
LogRateLimitIntervalSec=30s
LogRateLimitBurst=200
EOF
sudo systemctl daemon-reload
```

That says "no more than 200 messages every 30 seconds from this unit, then start
dropping." Check it landed with:

```
systemctl show mqtt2cmd.service -p LogRateLimitIntervalSec -p LogRateLimitBurst
```

Drop-ins are worth getting comfortable with generally. They apply to any unit
setting, they survive package updates, and `systemctl cat mqtt2cmd` shows you
the original file plus every drop-in stacked on top, in order.

#### If you went read-only, remember it applies to everything

`mqtt2cmd` lives in `/home/pi` too, so the same two-reboot dance applies to
updating it, and anything it writes next to itself disappears at reboot. This is
the part of the read-only decision that is easy to forget, because you make the
decision while thinking about one application and then live with it across all
of them.

### The boot takes 1m41s, and it is essentially one service

While I had the stopwatch out, I finally measured the thing I had been vaguely
tolerating for years:

```
systemd-analyze
systemd-analyze blame | head
```

After trimming the box down, the boot is **13.5 s of kernel plus 1 min 27.6 s of
userspace**, so 1 min 41.0 s in total. Which tells you immediately where not to
look: the kernel is not the problem, and neither is the SD card being slow to
hand off. It is all userspace, and it is not spread around at all either:

| Service | Time |
| --- | ---: |
| `NetworkManager.service` | **59.9 s** |
| `oclock-strip-spi.service` | 15.0 s |
| `dev-mmcblk0p2.device` | 13.0 s |
| `systemd-rfkill.service` | 6.2 s |

NetworkManager is **59% of the entire boot**. The strip binder's 15 seconds, by
contrast, is load-bearing -- that is the wait loop from the udev story above,
doing exactly what it should, and I am leaving it alone.

So I went looking, and the journal has the answer, or at least most of it.
Inside NetworkManager's startup there are repeated systemd daemon-reloads:

```
[60.98] Reload requested from client PID 454 ('systemctl') (unit NetworkManager.service)
[66.11] Reloading finished in 5121 ms
[70.36] Reload requested from client PID 490 ('systemctl') ...
```

**Five seconds. Per reload.** On a desktop a `daemon-reload` is something you
type without thinking about it -- it is imperceptible. On a 1 GHz single-core
ARMv6 reading a slow SD card, systemd re-parsing every unit on the system is a
five second job, and several of them back to back is most of a minute.

That is the shape of a lot of Pi Zero performance work, honestly. Nothing is
broken. An operation that is genuinely free on normal hardware just is not free
here, and something is doing it in a loop.

Two contributing details I found while poking at it, both worth a look on your
own box:

- There is a **phantom netplan profile for `eth0`** -- `match: {}`, DHCP for
  both v4 and v6, autoconnect on -- on a board that has no ethernet port at all.
  There is no `eth0` in `/sys/class/net` for it to ever match.
- Every reload re-runs the fstab generator, which then grumbles about the fstab
  overlayroot rewrote: `Checking was requested for /media/root-ro/, but it is
  not a device`. Harmless, but it is work being redone each time.

**I have not fixed this, and I would not want you to take a fix from me here.**
Removing that eth0 profile needs the root filesystem writable, so it waits for
the next deploy window, and until I have measured the boot afterwards I do not
actually know that it helps. Diagnosis is not a fix. This is where I am.

What makes it fit the rest of the post is that none of it is new, and the
overlay did not cause any of it. It was presumably always like this, through the
entire decade this clock has been on the wall. It simply never got measured,
because nothing ever forced me to stand in front of the thing with a stopwatch.
Turning a box read-only makes you reboot it a lot, and rebooting it a lot is how
you find out what your boot actually costs.

### The grep that matched itself

Ending on the cheapest one, because it cost me a genuinely alarming ten minutes.

After the first power cut I went looking for read-only violations, grepping the
journal for `EROFS`. And I found one. On a box that had just been through an
unclean shutdown, that is exactly the sort of thing that makes you sit up.

It was my own command. I was logged in over SSH, the session was being logged
to the journal, and the log line contained the full command line I had just
typed -- which, naturally, contained the string `EROFS`. I had grepped for a
word and found the grep.

So filter out the SSH daemon's own records before you go looking:

```
journalctl -b | grep -i erofs | grep -v 'sshd'
```

Obvious in hindsight. Every "search the logs for X" habit has this hole in it,
and it shows up precisely when you are stressed enough to be searching the logs
in the first place.

### The one thing all of them had in common

Look back at everything that went wrong here and it is the same thing wearing
different hats:

- `systemd-remount-fs` **failed**, and nothing was wrong with the filesystem. It
  was faithfully applying a config file that only exists inside the overlay.
- **Swap disappeared**, and the read-only root had nothing to do with it. It was
  a `Requires=` edge onto that failing remount unit, three hops away.
- The strip binder **failed to settle**, while its own device was bound
  perfectly. An unrelated probe was holding the global udev queue open.

In all three, *the component reporting the failure was not the component with
the problem.* On a box wired together this densely, an error message is a place
to start looking, not an answer. Chase the dependency edge, not the wording.

That is also the argument against triaging a failed unit as cosmetic because its
job sounds irrelevant. "A remount that gets skipped on a read-only filesystem"
sounds like the safest thing in the world to ignore, and ignoring it cost me all
of my swap without a single message saying so.

#### And then it happened again, to me, in the middle of writing this

The best example is the one I walked into while the pattern was already fresh in
my head, which I think says something about how little help knowing the pattern
actually is.

After trimming all those services, I re-enabled the overlay, rebooted, logged
back in -- and the overlay was **off**. My immediate theory was tidy and
satisfying: `apt autoremove` had followed the dependencies a little too
enthusiastically and taken the `overlayroot` package with it. Of course it had.
I had just removed 58 packages. That is exactly the kind of thing that bites
you.

It was completely wrong. `overlayroot` was installed. `cmdline.txt` was correct.
`get_overlay_conf` returned 0, meaning the overlay was properly configured to
come up on the next boot.

The answer was sitting in the failed-unit list the whole time:

```
● run-p3725-i3726.service   failed   [systemd-run] /sbin/reboot
```

**The reboot had failed.** The machine never restarted. It was still running the
session from before I enabled anything, which is precisely what a
correctly-configured overlay that has not been rebooted into looks like.

There was nothing wrong with the overlay, nothing wrong with `overlayroot`, and
nothing wrong with the trimming. The component reporting the problem -- "the
overlay is off" -- was, once again, not the component with the problem.

It also explains why the two `raspi-config` queries are worth running as a
*pair*. `get_overlay_conf` said yes and `get_overlay_now` said no, and I had
been reading that as a contradiction to be explained. It is not a contradiction.
It is the tool telling you, precisely, that you have not rebooted yet.

### And then I pulled the plug

The closing note, which I am pleased to be able to write: **I did pull the
plug.** Three times, at the wall, ten seconds off, no warning. All three came
back clean -- checksums matched, no service restarted, the display was correct,
and the ext4 mount count never moved off 15, because a read-only mount does not
increment it.

The best moment was in the kernel log:

```
EXT4-fs (mmcblk0p2): orphan cleanup on readonly fs
```

The unclean cut left orphan inodes. ext4 spotted them and then refused to fix
them, because the filesystem is read-only. It would not write even to repair
itself. Every paragraph above is me arguing for that behavior; that one line is
the filesystem demonstrating it.


### Thanks

Big thanks to **Codex** and **Claude** for the assist on all of this -- a lot of
it was long, fiddly, measure-it-again work, and having a tireless pair to think
out loud with made it genuinely fun.

If something here was not well described, don't be shy about reaching out.

Enjoy!

{{< copy-buttons >}}

[part3]: post/hacks/office-clock-part3/ "Office Clock Project Part 3"
