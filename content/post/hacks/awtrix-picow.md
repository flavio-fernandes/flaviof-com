+++
author = "flaviof"
categories = ["hacks"]
date = "2026-10-19T18:54:00-04:00"
draft = false
tags = ["diy", "pico", "rp2040", "c++"]
title = "awtrix on a pico"
+++

AWTRIX NG is lovely firmware. The Pimoroni Galactic Unicorn is a lovely board. They had never met, so I introduced them.

<!--more-->

{{< figure src="img/awtrix-picow/unicorn.jpeg" alt="A hand holding the Galactic Unicorn: a long, thin black LED panel showing the time in white digits with a small red icon at the left end" caption="Note where the digits sit. Apps and icons live in the middle eight rows, with one row dark above and two below -- more on that later." >}}

If you have not met it: **AWTRIX NG is firmware for little LED matrix clocks.** You flash
it onto a board that has an LED panel on the front, and you get a clock that cycles through
apps -- time, date, weather, whatever you care to push at it -- plus an HTTP API, MQTT, a
web UI to set it all up, and a scripting engine for the things nobody thought of. It is
what a lot of people run on an Ulanzi desk clock, and on homemade ESP32 builds.

Here is why I wanted this. There is an [Ulanzi][ulanzi] on my desk running
[AWTRIX NG][awtrixng] and talking to Home Assistant, and it is one of those rare gadgets
that just works. It is stable, it is easy to set up, and it has never once asked me to
think about it. I also had a Galactic Unicorn, which is a much bigger and much prettier
panel, and what it had been running all along was MicroPython: an MQTT message scroller,
which I had taught to color its messages in [a pull request][scroller] back in 2024. It
was fun and it did work, but stable is not the word I would use for it -- and it was a
long way from what the Ulanzi was quietly doing right across the room.

So the motivation is not complicated: I wanted the firmware I liked on the panel I liked
looking at. I also wanted to know whether a Pico could carry the whole thing, which turned
out to be the more interesting question.

Credit where it belongs, before any of the technical part: [Blueforcer][blueforcer] and
the AWTRIX NG contributors built that firmware. Everything below exists only because what
they wrote was clean enough and careful enough that a port was thinkable at all.

One expectation to set: this is an experimental personal build. The code lives in a fork,
but a fork is not a product. I am not running a separate firmware distribution, and I am
not signing up to maintain one.

### What a Galactic Unicorn is

It is a 53x11 LED panel from [Pimoroni][gu] with a Raspberry Pi Pico W or Pico 2 W on the
back. Buttons down one side, a light sensor, a little speaker, and that is the whole
device. No soldering, no wiring, no enclosure to print. You hold BOOTSEL, plug in USB, drop
a `.uf2` on it, and it is a different gadget than it was a minute ago.

That last part is half the appeal, honestly. The feedback loop on a board you can reflash
by dragging a file is wonderful.

{{< figure src="img/awtrix-picow/effects.gif" alt="The LED panel animating: a green waveform filling from the bottom, then a game of Pong with white paddles at each end and a red ball" caption="A few of the built-in screens, one after another. Backgrounds, effects and games get the whole panel -- they are not confined to the middle eight rows." >}}

That is AWTRIX NG. The real thing: the same HTTP and MQTT API, the same web UI, the same
Home Assistant discovery, the same Berry scripting. A handful of features that depend on
hardware this board does not have are missing, and they are listed honestly at the end.

**If you have one of these in a drawer**, [the Galactic Unicorn guide][guguide] is your
next step. Which `.uf2` to drag, what the buttons do, how Wi-Fi setup works, and what the
limits are.

### What it looks like from Home Assistant

This is the part my DIY friends ask about first, so let me get to it early: nothing special
happens here, and that is exactly the point.

Switch MQTT on, switch discovery on, and the board announces itself to Home Assistant as a
single device, with lights and selects and buttons and sensors built from the hardware it
actually has. There is no YAML to write for that part and no custom integration to install.
The Unicorn on my bench turns up the same way the Ulanzi does.

For the things you *do* want to drive yourself, every action has one command topic and the
payload is plain JSON. The automation action that throws a message on the panel is this
short:

```yaml
action: mqtt.publish
data:
  topic: awtrix_galactic2w/cmd/notify
  payload: >-
    {"text": "washer done", "textColor": "#00DDFF"}
```

Two things to change for your own: `awtrix_galactic2w` is this board's MQTT prefix, so put
yours there instead -- the web UI shows it under **System -> MQTT** -- and all of this
assumes Home Assistant already has its MQTT integration talking to a broker.

{{< figure src="img/awtrix-picow/homeAssistant.png" alt="The LED panel showing the words WASHER DONE in cyan capitals" caption="A framebuffer capture, read back off the device through `/api/v1/display/screen`." >}}

The HTTP body and the MQTT payload are deliberately the same JSON -- *anything you can
`curl` you can publish*, as the reference puts it. So you can work an automation out at the
command line and then paste the payload straight into Home Assistant, which is exactly how
the one above was made.

### The architecture gave me a head start

Here is the thing that surprised me most, and it is a compliment to the people who wrote
AWTRIX NG: **the design was already asking for this.**

By the time I started, the firmware already had more than one platform. There is an
`esp32`, there is a `linux` app, and there is `tc002` for the Ulanzi TC002, which is Linux
running on the device itself. Adding `rp2040` next to them was joining a pattern, not
inventing one.

The whole Pico platform is **51 files and about 72 KB of source**. That is it. Everything
else -- the apps, the effects, the API, the scripting engine, the web UI -- is shared code
that did not care what chip it was running on, because somebody had already been careful
about that.

The rule that makes it work is written down in the project's own PR checklist:
`src/core/` stays portable. No Arduino headers, no FastLED, no board headers. I had to
respect that rule rather than invent it, and respecting it is what kept the port from
turning into a swamp.

### The panel is the fun part

If you read one section of this, read this one.

The Galactic Unicorn's panel is 1 bit per channel. Each LED has a red, a green and a blue
element, and each of those can only be fully on or fully off. There is no dimming in the
hardware anywhere. Every shade you see has to be made out of **timing**.

The way you get 14 bits of brightness per channel out of that is **binary code
modulation**, and it is one of those ideas that is obvious only after somebody shows it to
you. You draw the same frame 14 times, once per bit plane. Plane 0 you leave on screen for
1 tick. Plane 1 for 2 ticks. Plane 13 for 8,192 ticks. Your eye adds it up. There is no PWM
counter anywhere, no timer interrupt, no per-pixel math at display time -- just a stream of
bytes where the dwell time is baked in.

The stream is laid out so the hardware can eat it without help. One row of one bit plane
is 60 bytes, and every byte has a job:

- **2 bytes of header** -- how many pixels are coming, and which row they belong to
- **53 bytes, one per pixel**, carrying three bits each: the red, the green and the blue
  bit for *this* plane
- **1 spare byte**
- **4 bytes holding `1 << plane`** -- the dwell, in ticks, sitting right there in the data

That last one is where "the dwell time is baked in" stops being a figure of speech. From
there it just multiplies up:

- a row of 14 planes is 14 x 60 = 840 bytes
- a whole frame is 11 x 840 = **9,240** bytes
- and there are two of them, so **18,480 bytes** of static RAM is the panel's standing cost

Then the RP2040 does the part that still makes me grin, and it needs two bits of vocabulary
first. **PIO** is a set of tiny programmable state machines that sit right next to the pins
and shift bits in and out on their own schedule. **DMA** channels copy blocks of memory
from one place to another. The processor has to set both of them up; what it does not have
to do, once they are running, is anything at all to keep the panel refreshing.

So: a PIO program of **24 instructions** shifts the pixels out and burns the
binary-weighted dwell. One DMA channel streams the 9,240 bytes into that PIO program. A
second, tiny DMA channel does nothing but write the next frame's base address back into the
first channel's read pointer, and then chain back to it.

The two of them chase each other in a circle forever. **There is no refresh interrupt and
the CPU is not involved at all** -- not between frames, not during frames, not even while
the flash is being written. The panel keeps refreshing while the processor is off doing
something else entirely, which on a board this small is the difference between a display
and a slideshow.

{{< figure src="img/awtrix-picow/pioDma.svg" alt="Diagram: two frame buffers feed DMA channel 1, which streams into a PIO state machine, which drives the panel. DMA channel 2 writes the next frame's address back into channel 1 and chains to it. A dashed box shows the CPU is not involved." caption="Started once, then left alone. The only thing channel 2 ever writes is four bytes: where channel 1 should read from next." >}}

A few details I enjoyed:

- It asks for `pio1` before `pio0`, on purpose, to leave PIO0's instruction memory for the
  Wi-Fi chip. More on that fight in a minute.
- The state machine's clock divider is derived from the actual system clock, so the panel
  runs at identical timing on a Pico W and a Pico 2 W even though the chips do not run at
  the same speed.
- If it cannot get a PIO state machine or two DMA channels, it logs that plainly and the
  board **keeps running with a blank panel** instead of dying. A clock that admits it has
  no display is more useful than one that hangs.

The display half of this is adapted from [Pimoroni's own driver][pimoroni] (MIT), and they
deserve the credit for the hard parts of the panel timing. What is new is the 14-bit color
path, which applies AWTRIX's gamma exactly once, using NG's own gamma setting, rather than
Pimoroni's fixed 2.2.

It runs the built-in games at **42 fps**.

{{< figure src="img/awtrix-picow/tetrisAnimated.gif" alt="Tetris playing across the whole 53x11 panel, colored blocks stacking up from the bottom and a piece falling at the top left" caption="Games get all eleven rows. Compare with the photo at the top, where the clock keeps to the middle eight." >}}

### Eleven rows

The band AWTRIX draws its content into is eight rows high. That is what the icons are
sized for, what the built-in apps are laid out for, and what the scrolling fonts are drawn
against -- and that shared assumption is a good part of why the icons and apps people pass
around just work on somebody else's clock.

The Unicorn has eleven.

The fix was 29 lines in `core/render/ContentBand.h`. What those lines do is hand every
8-row-assuming part of the firmware a **clipped view into the middle of the real pixel
buffer**: same memory, same eight-row coordinates, just offset vertically. Deciding how
far down is the easy half:

```
inline constexpr int kContentBandHeight = 8;

inline int contentBandTop(int height) {
  return height > kContentBandHeight ? (height - kContentBandHeight) / 2 : 0;
}
```

The rest of the header builds the view itself. Because that view still speaks in eight-row
coordinates, every font keeps its baseline, every glyph keeps its clipping, and not one
line of scroll math had to change. Rows count from zero, so on an eleven-row panel the band
is rows 1 through 8: one row left dark above it, two below. On a 32x8 panel nothing moves
at all.

{{< figure src="img/awtrix-picow/proverb.gif" alt="The LED panel scrolling the words 'When one door closes, another door opens' in magenta, with the top row and the bottom two rows unlit" caption="The band, in action. In every frame of this one, not a single lit pixel falls outside rows 1 through 8." >}}

Backgrounds, effects, overlays, transitions and charts are *not* banded -- those get the
whole canvas, which is the entire point of having a taller panel. Scroll back up and you
can see it: the effects and the game run right to the edges, and the text does not.

Panel heights from 8 to 16 now work on **every** board, not just this one.

#### The landmine I set for myself

This one cost me an embarrassing afternoon, and it is entirely my own fault, which is why I
like it.

AWTRIX NG does not have a panel height setting. It has `panelWidth`, and the height is
simply eight. And because the height is not a setting, `pheight` sits in the list of
retired keys that the save path **erases**, so that boards upgrading from older firmware
stop carrying a dead value around. That is correct housekeeping, and I would have written
it the same way.

Then I came along and added panel height back.

So the setting was written to flash, and then, a few lines later in the same save, the
cleanup for the feature's own retirement deleted it again. The board reported the height
you asked for right up until it rebooted, at which point it was eight rows once more.
Nothing crashed and nothing logged, because from the firmware's point of view everything
worked exactly as designed.

The fix was deleting one string from one array. Finding it took considerably longer.

The lesson I am taking away: **a cleanup list for a removed feature is a landmine for
whoever brings that feature back.** The entry is invisible, it lives nowhere near the code
you are writing, and it does precisely what it was written to do. If you ever retire a
setting, it might be worth leaving a comment on its headstone.

### Four things that fought back

#### The radio and the display both want PIO

The CYW43 Wi-Fi chip needs PIO instruction memory and a state machine. So does the panel.
There are not many of either.

Worse, the Arduino core for the Pico brings the radio up **before `setup()` ever runs**, so
by the time any of my code exists, the radio has already taken what it wanted.

The fix is two linker wrappers:

```
-Wl,--wrap=init_cyw43_wifi
-Wl,--wrap=cyw43_cb_process_async_event
```

The first one defers the Wi-Fi bring-up until the display has claimed its PIO and DMA. The
display, as mentioned, politely prefers `pio1` and leaves PIO0 alone. Audio comes third,
by design, so it cannot steal from the radio either.

The second wrapper is pure debugging luxury: every CYW43 event -- type, status, reason,
which AP, what join state -- gets logged. When a link drops at 2am, the device log says why.

There is also a 20 millisecond self-check that runs after Wi-Fi comes up. It watches the
DMA read address and logs `refresh advancing` or `refresh NOT advancing`. It answers
exactly one question -- "did the radio just steal my panel?" -- and it answers it in the
log instead of in my imagination.

#### One missing linker flag

This one is my favorite bug of the whole project, purely for blast radius per character.

The Arduino core's PlatformIO builder **omits `_printf_float`**. Its Arduino IDE
configuration adds it; the PlatformIO path does not.

So: every float in the JSON API rendered as nothing at all.

```
{"lightLevel":,"...
```

Which makes the JSON unparseable. Which makes the web UI fail to read the device state.
Which makes the web UI conclude the device is unconfigured, and **drop into the Wi-Fi setup
screen** -- on a board that was sitting happily on the network the whole time.

I spent a while on the wrong floor of that building. The fix:

```
-Wl,-u,_printf_float
```

Twenty characters. :)

#### Five sockets, eight requests

Open the AWTRIX web UI and your browser fires off eight requests at once. The Pico's lwIP
has **five TCP sockets**. Five of those requests get a socket; the other three arrive to
find the pool full.

That alone would be fine -- the latecomers would just wait their turn. What was not fine is
that accepted clients were given minimum priority while the listening socket sat at normal
priority. So when request number six knocked, lwIP made room for it by **aborting one of
the five live connections** instead of leaving it to wait. Two or three of the eight would
die with a reset, and the UI would load half-empty.

Running the listener at the same priority as its clients turns that abort into a dropped
SYN, and a dropped SYN is just a browser retry. Nobody notices.

There was a second-order trap waiting underneath it, too: lwIP reports that dropped
connection as an accept callback with a null pointer, and the server class would wrap the
null and fault on it. Which it did, on my bench, under load -- the board hard-faulted and
froze solid, no ping, no serial, and the next flash attempt failed because it could not even
reach BOOTSEL. That one needed a human to walk over and pull the USB cable.

#### An eight-second watchdog versus a very patient client

The RP2040's hardware watchdog maxes out around **8 seconds**, and AWTRIX handles a whole
HTTP request and its response inside one pass of the main loop. The Arduino web server's
timeouts restart whenever a byte moves.

Put those together and a client that sends one byte every two seconds can hold the loop
open forever, and the watchdog reboots the board. Not maliciously -- a phone on bad wifi
does this by accident.

The fix was to stop trusting the client's pace anywhere, with a separate deadline in each
direction.

Coming in, the clock is on *arrival*. Headers go into a bounded buffer and anything past
2 KB of them gets a 431 and a closed connection. A client then has **5 seconds** to deliver
those headers and the first 2 KB of body, and is dropped if it has not managed that. A body
longer than 2 KB keeps feeding the watchdog as it arrives, one network segment at a time.

Going out, the response is written in whatever size the send buffer has room for right now,
feeding the watchdog between pieces. Here the **5 seconds** covers the whole response
rather than each piece of it, so a reader that has stopped reading is given up on outright
-- a 40 KB file that used to hold the loop for 40 seconds now lets go after about 5.

My favorite small bug in this pile: the reset reason has to be read **once, before the
watchdog is armed**. Read it later and an ordinary reboot -- say, the one right after you
flash the board -- reports itself as a watchdog reset. I spent a few minutes being very
confused by a board that insisted it had crashed when it had merely been reflashed.

And the honest ending, because this is the kind of thing it would be easy to oversell: this
is **not** completely solved. A body over 2 KB sent slower than roughly 180 bytes per second
can still trip the watchdog. It is written down as a known limit rather than papered over.

### Testing a board you are not holding

This is the part I would most like someone to steal.

Almost all of the Pico-specific logic that *can* be pure, is pure. The bit-plane packing,
the color lookup table, the button debouncing, the geometry rules, the orientation
transforms -- all of it lives in headers with no SDK and no Arduino dependency, and all of
it is tested on a laptop in about a second. The header that does the panel packing says so
right at the top: *no SDK/Arduino dependencies: host-testable*.

On top of that:

- **`tools/container/ci-local.sh all`** runs the same gates CI runs, in a container, with no
  toolchain installed on the host: host tests, every build variant, the web UI tests, the
  docs checks. I ran it on **every one of the 27 milestone commits, and all 27 passed.** Not
  because I am virtuous, but because a 300-file change that can only be reviewed as one blob
  is not really reviewable at all.
- **`tools/pico/smoke.sh`** is about 110 HTTP calls, one per line, PASS or FAIL. The design
  decision I am happiest with: every write it makes, it undoes on exit. That means you can
  point it at a board you actually use, repeatedly, without it leaving junk behind.
- **`tools/pico/burst.sh`** fires the exact eight requests the web UI opens on load, ten
  rounds, eighty requests. That is the script that found the socket-priority bug, and the
  one that hard-faulted the board.

And then the real board, on a bench, with a camera pointed at it, for everything a host test
cannot know: that the panel is actually lit, that the letterboxed 8-row mode lands on the
right rows, that melodies come out of the speaker at every volume step, that the watchdog
really does recover from a deliberate hang.

Here is the thing nobody tells you about hardware projects: the hard part is not writing the
code, it is **knowing whether it works**. Pushing as much as possible into pure functions
tested on a laptop is how you get to spend your bench time on the questions that genuinely
need a bench.

For the record, where it ended up:

| | Pico W | Pico 2 W |
| --- | ---: | ---: |
| RAM | 104,460 (39.8%) | 110,896 (21.2%) |
| Flash | 1,101,328 (70.2%) | 1,095,164 (29.9%) |
| Script heap | 48 KB | 96 KB |

The Pico W fits with every feature turned on, which I genuinely did not expect when I
started.

### A much smaller thing, sent the right way

Somewhere in the middle of all this I wanted something simple: a Berry app that shows a
different random background effect each time it comes around. **Berry** is the small
scripting language AWTRIX NG embeds, so you can add behavior to a display without building
firmware.

So I wrote one. And it had to start like this:

```
self.names = ["BrickBreaker", "Checkerboard", "ColorWaves", "Fade", "Fireworks",
              # ... thirteen more, typed out by hand ...
              "TwinklingStars"]
```

Nineteen effect names, pasted into a script, going stale the moment the firmware adds or
renames one. The firmware knows this list perfectly well -- it serves it from
`/api/v1/capabilities` -- but a script could not ask for it.

So that became [an issue][issue106] and then [a small pull request][pr107] upstream, adding
two globals next to the existing `effect()` and `overlay()` calls:

```
effects()    # ["BrickBreaker", "Checkerboard", "ColorWaves", ...]
overlays()   # ["drizzle", "frost", "rain", "snow", "storm", "thunder"]
```

They return the effect registry's own list -- the exact same vector `/api/v1/capabilities`
serves -- so the two can never disagree with each other. **508 bytes of flash, zero RAM**,
on the ESP32 build. And not one line of it has anything to do with a Pico.

One detail I liked solving: the script has to run on firmware that does not have this yet,
and in Berry a bare call to a function that does not exist will not even *compile*. So it
goes looking through the `global` module instead, and falls back to the embedded list when
the call is not there. One script, both firmwares. The whole thing is about fifty lines --
[here it is as a gist][randomfx], ready to paste into the web UI.

If you would rather do it from Home Assistant and skip scripting entirely,
[this blueprint][blueprint] does the same job over MQTT. It is a port of N1c093's AWTRIX 3
flow, and it works on any AWTRIX NG display -- no Pico required.

### About upstream

When I finished the first version of this port, I posted about it on the AWTRIX Discord and
opened a PR.

Blueforcer answered quickly and plainly, and his reasons were good ones. Eleven rows is a
format nothing in the ecosystem assumes: the icons and apps and scripts that AWTRIX users
share with each other are built for 8 or 16. Supporting the heights in between is real
ongoing work, for the firmware and for the AWTRIX Hub behind it. And the architecture was
about to be reworked, so the PR would break.

He was right on all three, and most right on the last one. The rework landed, my PR broke
completely, and the port I am writing about is a **re-port** onto the new design rather than
a rebase -- I threw the old one on the floor and did it again, following the new structure.
Being told that early, by somebody who could have just said nothing, saved me from finding
it out the hard way.

Whether another chipset belongs upstream is a maintainer's call and nobody else's. More
platforms and more panel sizes mean more to support, and no amount of tidy code makes that
cost go away.

The one thing I would still love to see someday: a **Pico W / Pico 2 W DIY** square
sitting next to "ESP32 DIY" and "ESP32-S3 DIY" on the [AWTRIX NG site][awtrixng]. Not this
strange eleven-row board -- a Pico 2 W driving an ordinary off-the-shelf 32x8 matrix, which
is eight rows like every other DIY build, where the only thing that changed is which
microcontroller is on the back. The work is parked where it can be found.

### Where everything is

Everything is public.

- The port: [PR #12][pr12] -- 31 commits, 323 files, merged into [`main-picow`][picow].
  `main` on that fork stays in sync with upstream.
- The first version, on the older base: [PR #1][pr1].
- [The Galactic Unicorn guide][guguide] -- flashing, buttons, Wi-Fi setup, what each build
  has and does not have, and an honest list of known limits.
- [The display engineering page][gudisplay] -- the PIO/DMA details above, in much more
  depth.
- [How settings are stored][gupersist] -- there is no NVS on a Pico, so there is a small
  atomic key-value format on LittleFS instead.
- The small upstream contribution: [issue #106][issue106] and [PR #107][pr107].

Things it does not do, so nobody gets surprised: no MP3 or internet radio (it plays
melodies through a tone output, not a decoder), no outbound TLS, and no firmware update from
the browser -- there is no second firmware slot in the Pico's flash layout, so updates are a
UF2 over USB. There is no battery and no temperature sensor, because the board does not have
them.

One more thing, because it belongs next to the downloads rather than buried. Blueforcer
has asked that forks not use his AWTRIX Hub, and that is entirely his to ask. The firmware
here never contacts it -- that is upstream's design, not anything I added. What is left is
the web UI, which I took from upstream unchanged and which goes looking for icons and
script updates in your browser, the same way it does on any AWTRIX NG device. I have left
it the way upstream ships it, and written that down here rather than let somebody find it
in a packet capture.

### Thanks

To **Blueforcer** and everyone who has contributed to AWTRIX NG: thank you. For the
firmware, for the Hub, for answering a stranger's question, and for being straight with me
about what you could and could not take on. The architecture you built is clean enough that
a port like this was possible for one person in their spare time, and that is not an
accident -- that is design.

To **Pimoroni**, for the Galactic Unicorn and for publishing the driver that taught me how
its panel actually works.

And to **Claude**, for the assist. This project had a lot of long, fiddly, measure-it-again
work in it -- PIO timing, DMA chaining, watchdog budgets, a linker flag hunt that went on
much too long -- and having a tireless pair to think out loud with made it genuinely fun.
It helped me put this page together, too.

Thanks for reading this far. If something here is wrong or unclear, please do reach out --
I would rather know.

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

[awtrixng]: https://blueforcer.github.io/awtrix-ng/ "AWTRIX NG"
[blueforcer]: https://github.com/Blueforcer "Blueforcer on GitHub"
[ulanzi]: https://www.ulanzi.com/products/tc002-pixbar-smart-pixel-clock-ii "Ulanzi TC002 Pixbar"
[gu]: https://shop.pimoroni.com/products/galactic-unicorn "Pimoroni Galactic Unicorn"
[pimoroni]: https://github.com/pimoroni/pimoroni-pico "Pimoroni Pico libraries"
[pr12]: https://github.com/flavio-fernandes/awtrix-ng/pull/12 "Galactic Unicorn on AWTRIX NG 1.2.2"
[pr1]: https://github.com/flavio-fernandes/awtrix-ng/pull/1 "The first Galactic Unicorn PR"
[picow]: https://github.com/flavio-fernandes/awtrix-ng/tree/main-picow "main-picow branch"
[guguide]: https://github.com/flavio-fernandes/awtrix-ng/blob/main-picow/docs/advanced/galactic-unicorn.md "Galactic Unicorn guide"
[gudisplay]: https://github.com/flavio-fernandes/awtrix-ng/blob/main-picow/docs/advanced/galactic-unicorn-display.md "Galactic Unicorn display notes"
[gupersist]: https://github.com/flavio-fernandes/awtrix-ng/blob/main-picow/docs/advanced/pico-persistence.md "Pico persistence"
[issue106]: https://github.com/Blueforcer/awtrix-ng/issues/106 "Scripts: list the built-in effect and overlay names"
[pr107]: https://github.com/Blueforcer/awtrix-ng/pull/107 "effects() and overlays()"
[scroller]: https://github.com/ucl-casa-ce/Galactic-Unicorn-MQTT-Scroller/pull/6 "Galactic Unicorn MQTT Scroller: message colors"
[randomfx]: https://gist.github.com/flavio-fernandes/5e728cb4f65b3790777925b020d96fe1 "RandomFX.be"
[blueprint]: https://gist.github.com/flavio-fernandes/e4d4c5f5a113193eea0518ca4ca01b64 "AWTRIX NG random effect blueprint for Home Assistant"
