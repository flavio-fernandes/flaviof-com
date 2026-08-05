+++
author = "flaviof"
categories = ["hacks"]
date = "2026-08-13T23:05:00-04:00"
draft = false
tags = ["diy", "rpi", "linux", "networking"]
title = "five wrong theories about a raspberry pi wifi problem"
+++

The office clock kept falling off the network. Five theories died before I built
something that could actually see the failure, and the thing that finally found
it was a median.

<!--more-->

Same box as always: the Raspberry Pi Zero W that has been running a clock on my
office wall since 2016. [Part 3][part3] covers its 2026 software rebuild, and
[the read-only gotchas post][gotchas] covers making its root filesystem
read-only. This one is about the week after, when it would not stay on wifi.

The symptom was simple and awful. Every so often the clock would vanish from the
network. The display kept running, the board was clearly alive, but nothing
answered -- `ssh` said `No route to host`, which is ARP failing, which means it
was not on the network at all any more. Sometimes it came back on its own after
a few seconds. Once it stayed gone for six and a half hours.

I have a cron job called `poke` that pings the clock every fifteen minutes and
power cycles it through a smart switch if it does not answer. So in practice the
clock always came back. That turned out to be the whole problem.

### The evidence was destroyed by the recovery

Here is the trap, and it took me embarrassingly long to name it out loud.

The root filesystem is read-only with `overlayroot=tmpfs`, so `/var/log` lives
in RAM. The recovery for a wedged clock is a power cycle. **A power cycle wipes
RAM.** Every single time the box failed, the thing that fixed it also deleted
the only record of what happened.

So I would come back to a healthy clock, run `journalctl`, and find a log that
started at the reboot. Nothing before it. Ever.

That is why I burned five theories:

1. **The wifi firmware was updated recently.** It was not -- I had misread the
   mtime of a dpkg `.list` file. The actual blobs were weeks older.
2. **A systemd watchdog was resetting the box.** `bootstatus: 0`. The reboots
   were my own `poke` script doing its job.
3. **The kernel command line had changed.** I compared a file on disk against
   `/proc/cmdline` and nearly presented that as a diff. They were byte-identical.
4. **A stale lock file was latching the box into a reboot loop.** Plausible, and
   a real bug -- more on it below -- but not this.
5. **Something in the logs was failing silently.** The check I was relying on
   turned out to be `file /var/log/syslog`, and `file` exits 0 whether or not the
   path exists. It had been validating nothing for years.

Five theories, all argued from fragments, none of them measurable. Every one of
them was a story I told about a gap in the data.

### So build something that survives the failure

The fix for that is not cleverness, it is a vantage point. Put the observer
somewhere that stays up.

I already run Uptime Kuma in a container on my Proxmox box, and that container
can reach the clock. So it got a small flight recorder: a shell loop that, every
**five seconds**, sends one ICMP echo and opens one TCP connection to port 80,
and every thirty seconds fetches the clock's own `/status.json`. All of it
read-only against the clock -- nothing installed on the Pi, nothing written to
it, no new firewall rule, because port 80 was already open to that subnet.

Five seconds mattered. The outages I eventually caught were as short as **one
second**, and the whole reason `poke` had never reported a problem is that a
fifteen-minute sampler essentially never lands inside a five-second window. Both
observers were telling the truth. Only one of them could see.

The other design decision that mattered: **record latency as a number, not as a
verdict.** My first instinct was a short HTTP timeout and an up/down boolean.
That would have thrown away the entire answer, because the clock was rarely
*down*. It was slow.

### The median was the answer, and it was hiding in plain sight

After a night of recording, the table looked like this. `p50` is the median
round trip in milliseconds.

```
  HOUR      SAMPLES   ICMP%  RTT_p50  RTT_p90  RTT_p99  RTT_max
  21            718   100.0     6.09     10.4     40.3      391
  22            718    98.9     48.9      465     2025     2758
  23            719   100.0      126      527      977     2205
  00            718    99.9      127      554     1319     2286
  03            715    99.2     99.2      390     1033     1772
  06            717   100.0     90.8      339      737     1012
```

Six milliseconds in the evening. **A hundred and twenty in the middle of the
night**, for eight hours straight, at a rock-steady -45 dBm with zero missed
beacons and essentially no packet loss. Not down. Just twenty times slower, and
only when nothing else was talking to it.

An 802.11 beacon interval is 100 TU, which is **102.4 ms**.

A station in power save mode does not receive unicast frames while it is
asleep. It wakes on a beacon, checks whether the access point has anything
buffered for it, and only then collects it. So the round trip is not "slow
wifi" -- it is being **quantised to beacon boundaries**. A median sitting on one
beacon interval is not a coincidence, it is a fingerprint.

And it explains the correlation that nothing else explained: the degradation
tracked *network idleness*, not time, temperature, signal, or load. Evening
traffic kept the radio awake. Overnight, every probe paid the full beacon tax.

The clock's own kernel log had been saying so from the beginning:

```
brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled
```

### Turning it off, and the check you must not skip

NetworkManager can disable it. The connection here is generated by netplan and
could be regenerated, so the right place is a drop-in rather than the connection
profile:

```
# /etc/NetworkManager/conf.d/10-wifi-powersave.conf
[connection]
wifi.powersave = 2
```

`0` = use default, `1` = leave alone, `2` = disable, `3` = enable.

Now the trap. After applying that, `nmcli` reports:

```
802-11-wireless.powersave:   0 (default)
```

That looks like it did not work. It is correct and expected -- the value arrives
as a *default* from `conf.d`, so the per-connection property legitimately stays
unset. The authoritative check is the kernel:

```
$ sudo dmesg | grep power_mgmt
[95.645394]  brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled
[98.587963]  brcmfmac: brcmf_cfg80211_set_power_mgmt: power save disabled
```

NetworkManager enables it at association, then the drop-in turns it off three
seconds later. **If you do not see that second line, nothing happened**, no
matter how green everything else looks.

There is a bonus in doing it this way. Because it is a default rather than a
connection property, it re-applies automatically any time the driver reloads --
which matters later.

The result, over the following days:

|  | power save on | power save off |
|---|---|---|
| RTT p50 (idle hours) | 99-127 ms | **6.0 ms** |
| RTT p90 | 340-554 ms | **10.3 ms** |
| RTT p99 | 740-1320 ms | **33-54 ms** |
| ICMP success | 99.0-99.9% | **100.00%** |

Two consecutive full days at 100.00%, out of seventeen thousand pings each.

### The part where I was wrong

This is the honest bit, and it is the reason I did not stop here.

I wrote "power save was the cause" in my notes. It was not -- or rather, it was
the cause of *the latency*, which is a different claim from the one that
mattered. The clock was still wedging.

The six-and-a-half-hour outage happened with power save **already disabled**. I
was able to prove the setting had really been in effect, and prove it after the
fact, because the flight recorder had been storing the clock's own
`/status.json` every thirty seconds -- and that JSON contains a couple of
monotonic counters. A reboot resets them. They never reset. The box had not
restarted, so the runtime setting had not silently reverted.

That is the payoff of storing the whole payload instead of the two fields I
thought I needed at the time.

The run-up to that outage is the clearest picture I have of the real failure:

```
00:34:55  icmp 6.22 ms  tcp 5 ms
00:35:00  icmp 5.69 ms  tcp 5 ms     <- perfectly healthy
00:35:12  icmp FAIL     tcp FAIL     <- gone, for 6h37m
```

No ramp. No rising latency, no loss creeping up. One sample healthy, the next
silent, and no link-layer event anywhere in the driver log. That is a chip or
driver wedge, and I still do not know what causes it. Old Broadcom firmware from
2021 with no diagnostics is a bad thing to go hunting.

So I stopped hunting and made recovery cheap instead.

### A watchdog, and how it lied to me

The watchdog is thirty lines of shell. It pings the gateway every 30 seconds. At
two minutes with no answer it asks NetworkManager to re-associate. At four
minutes it reloads the wifi driver. It **never reboots** -- `poke` is still the
outer backstop -- and it will not act at all until it has seen the gateway work
once, so a slow boot can never trigger a driver reload.

Then I did the thing I very nearly skipped: I tested it.

Test one, taking the interface down, passed exactly as designed. Test two, the
driver reload, printed this:

```
modprobe -r brcmfmac   ->  REMOVE FAILED
modprobe brcmfmac      ->  reloaded OK
```

Read those two lines together. The unload failed and the reload "succeeded."

`dmesg` settled it: the `brcmfmac` initialisation lines were still timestamped
`[49.x]`, from a boot three and a half days earlier. **The driver had never been
unloaded or reloaded.** What actually restored the network was the `nmcli`
reconnect at the end of the function -- the hard recovery had silently decayed
into a second copy of the soft recovery, which had already failed.

Two separate bugs, stacked.

The first:

```
brcmfmac_cyw    12288  0
brcmfmac       331776  1 brcmfmac_cyw
modprobe: FATAL: Module brcmfmac is in use.
```

Recent kernels split out `brcmfmac_cyw`, which depends on `brcmfmac`.
**`modprobe -r` unloads what your target depends *on*, never what depends on
your target.** So removing `brcmfmac` by itself can never work here. You have to
take `brcmfmac_cyw` first.

The second is the one worth carrying around:

> **`modprobe <module>` returns 0 when the module is already loaded.**

So a failed unload followed by a no-op load is *indistinguishable, by exit code,
from a real reload*. My watchdog checked those exit codes and reported
`reloaded OK, firmware re-downloaded` while doing absolutely nothing. In a real
wedge it would have logged success and left the clock dead until `poke` pulled
the power.

That is the worst failure mode a safety net can have. Not "it did not work" --
"it did not work and told me it did."

### Verify the end state, not the exit code

The fix is to remove the dependent module first, and then to stop believing
return values when a direct check is one command away:

```bash
modprobe -r "${MODULE}_cyw" 2>/dev/null
modprobe -r "$MODULE" 2>/dev/null

if lsmod | grep -q "^${MODULE} "; then
    log "ERROR $MODULE STILL LOADED after unload -- this recovery did NOTHING."
    return 1
fi
log "$MODULE unloaded (verified via lsmod)"
```

`modprobe`'s exit code meant nothing. `lsmod` meant everything. Same shape as
the `dmesg` check for power save earlier, and the same shape as that
`file /var/log/syslog` check that had been passing unconditionally for years.
Three times in one project, the trustworthy signal was a direct observation of
the end state and the untrustworthy one was a status code.

And the proof that the fixed version really works is itself an end-state check:

```bash
sudo dmesg | grep -c "F1 signature read"
```

That counts fresh chip probes. One at boot, plus one for every genuine driver
reload. It went from 1 to 2, with the firmware re-download logged in between,
followed by `power save disabled` re-applying itself from the drop-in. Real
recovery time, end to end: about **ten seconds**.

### Two smaller things that fell out of this

**A lock file with no owner will eventually hurt you.** My `poke` script touched
`/tmp/badoclock` before recovering and removed it after -- but with `set -o
errexit` in front of three fallible network operations, any failure left the
latch behind forever. After that, every run skipped the health check and went
straight to power cycling. I found one sitting there, hours stale. The fix is a
`trap ... EXIT INT TERM` so it always clears, plus an age check so a stale latch
expires on its own rather than waiting for a human to notice.

**Fixing one thing exposes the next one.** With the wifi stable, the clock ran
for three and a half days -- easily its longest stretch of the whole saga -- and
a slow memory growth in one of my own Python services became visible for the
first time. It had always been there. Frequent reboots had just been hiding it.
I have not touched it yet, because the shape of the curve (a full day at exactly
zero change, then a step) looks much more like CPython arena behaviour settling
into a working set than a real leak. It is being watched, with a number written
down that would make me act.

### So was this known? Yes. For about ten years.

I went looking afterwards, expecting to find nothing, and instead found the
thing already written down -- by Raspberry Pi, in their own kernel tree.

Commit [1f13305][rpicommit], by Phil Elwell:

> Disable wireless power saving in the brcmfmac WLAN driver. **This is a
> temporary measure until the connectivity loss resulting from power saving is
> resolved.**

It force-set `enabled = false` inside `brcmf_cfg80211_set_power_mgmt` and
printed `power management disabled`, overriding whatever userspace asked for.
The file it patches is `drivers/net/wireless/brcm80211/brcmfmac/cfg80211.c` --
and that path moved to `drivers/net/wireless/broadcom/brcm80211/` in kernel 4.7,
in mid-2016. So the commit is older than that.

It is not in the kernel my clock runs. I can prove that from the log I have been
staring at all week: mine prints the stock driver strings, `power save enabled`
and `power save disabled`. The patched driver printed `power management
disabled`, and with it in place power save could never have been switched on at
all.

Read that sequence again, because it is the actual story here. The exact failure
was found. It was acknowledged by the vendor of the board. A fix was shipped,
explicitly labelled temporary, pending a real one. The real one never arrived,
the temporary one was quietly lost somewhere in ten years of rebasing, and the
default went back to the setting that causes the problem.

A temporary measure that outlived its own removal.

Meanwhile [raspberrypi/firmware#1973][fw1973] is open, on the same BCM43430,
with `power save enabled` all through the logs. Module parameters were tried
there (`feature_disable=0x2000`) and did not help. The forums have years of
threads about this chip dropping off wifi, and most resolve the same way: a
stranger says turn power save off, the thread gets marked SOLVED, and nothing
goes anywhere.

And while I was writing this, somebody opened
[raspberrypi/linux#7533][rpi7533] -- Pi Zero W and Zero 2 W, same kernel series,
random disconnects, no log entries before the failure. Twelve days old when I
found it, no maintainer reply. They had already tried disabling power save, and
it had not helped.

That last detail is the one I would have misread a week ago. It looks like
evidence that power save is a red herring. It is not: it is evidence that **two
different bugs are wearing the same symptom.** Power save explains the latency,
demonstrably and reversibly. It does not explain the disconnects -- I have those
with it off too. Everyone hitting this ends up arguing about a single "wifi is
flaky" and getting contradictory results, because half of them measured one bug
and half measured the other.

### And the wedge is known too, which is the bad news

Everything above is about the *latency*. The other failure -- the radio going
silent until someone cuts power -- is also documented, and reading it made me
glad I did not delete the smart switch.

[openwrt/openwrt#23069][owrt] is the most careful writeup of it I found. Same
driver, newer chip (BCM43455, on a Pi 5). Once it enters its terminal state:

- `rmmod brcmfmac; modprobe brcmfmac` -- "same timeout", every attempt
- unbind/rebind the SDHCI platform driver, watching the regulator actually cycle
  -- still times out
- **a software `reboot` does not clear it**
- only "physical PSU unplug + replug recovers"

So there is a state in which my watchdog does nothing, a reboot does nothing,
and the only thing on the list that works is removing power. That is what `poke`
has been doing this whole time with a smart switch, and it turns out to be the
load-bearing layer rather than the crude one.

There is also a thread on Infineon's own forum about a CYW43455 getting stuck
with [`brcmf_sdio_bus_sleep error while changing bus sleep state -110`][ifxbus],
needing a module reload to recover. What is interesting is the path in: the bus
got stuck *during a power-save transition*. Which is at least a plausible thread
connecting the two halves of my week -- fewer sleep transitions, fewer
opportunities to wedge the bus. I want to be careful there, though: I cannot
show that from my own data. I had one wedge after disabling power save and none
since, and one event is not a rate. **Turning power save off demonstrably does
not eliminate the wedge.** It fixed the latency, and that is all I can claim.

### Why nobody is fixing it

`brcmfmac` is vendor-maintained. Infineon (who inherited these parts from
Cypress, who got them from Broadcom) ships a large stack of patches
[explicitly marked non-upstream][ifxrel], and is working on a replacement driver
for mainline rather than fixing the old one. The chip in my clock shipped in
2016 and its firmware is dated July 2021. It is nobody's priority, and honestly
I understand why -- it is just strange that the last word on it is a
decade-old commit saying "temporary."

So the complete set of documented recourses, as far as I can tell, is three
items long, and I am running all three:

| | what it is | how much I trust it |
|---|---|---|
| Disable power save | a `conf.d` drop-in | fixes the latency, measured |
| Reload the driver | the watchdog | works on a healthy chip; unproven on a wedged one |
| Cut the power | `poke` and a smart switch | the only one that always works |

No fourth idea exists that I could find. If you know of one, I would genuinely
like to hear it.

### What I would tell myself at the start

Put the observer where the failure cannot reach it. Record quantities, not
verdicts -- I would have missed this entirely with an up/down check, because the
clock was almost never down. Sample fast enough to see the events you are
chasing, then keep the raw payload so that the question you have not thought of
yet is still answerable in three days' time.

And test the recovery path. A watchdog you have never fired is not a safety net,
it is a belief.

And when you finally fix something, go and look for who else hit it. I assumed
that step would be a formality. Instead it turned a private annoyance into a
much stranger fact: this was found, acknowledged and patched before the clock on
my wall was two years old, and the patch is gone.

If something here was not well described, don't be shy about reaching out.

Enjoy!

{{< copy-buttons >}}

[part3]: post/hacks/office-clock-part3/ "Office Clock Project Part 3"
[gotchas]: post/hacks/readonly-rpi-gotchas/ "Read-only Raspberry Pi gotchas"
[rpicommit]: https://github.com/raspberrypi/linux/commit/1f133059e579d7aeef76ab8402b95eb4418e8ca4 "brcmfmac: Disable power management"
[fw1973]: https://github.com/raspberrypi/firmware/issues/1973 "Raspberry Pi Zero 2 W WiFi networking unusable"
[rpi7533]: https://github.com/raspberrypi/linux/issues/7533 "Raspberry Pi 0w and 02w random network disconnects"
[owrt]: https://github.com/openwrt/openwrt/issues/23069 "brcmfmac BCM43455 HT Avail timeout, only PSU cold boot recovers"
[ifxbus]: https://community.infineon.com/t5/AIROC-Wi-Fi-MCUs/CYW43455-brcmf-sdio-bus-sleep-error-while-changing-bus-sleep-state-110/td-p/403367 "CYW43455 brcmf_sdio_bus_sleep error -110"
[ifxrel]: https://github.com/Infineon/ifx-linux-wireless/blob/master/RELEASE.md "Infineon ifx-linux-wireless release notes"
