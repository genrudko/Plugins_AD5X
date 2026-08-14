# AD5X display build spike

This directory is an isolated feasibility spike for running upstream KlipperScreen on the stock AD5X 4.3-inch display under Z-Mod.

It is intentionally separated from the stable installer/runtime. Nothing in this directory should modify Z-Mod display lifecycle until the rendering stack is proven on hardware.

## Target facts currently treated as constraints

- Z-Mod runtime is inside `/usr/data/.mod/.zmod`.
- Target userspace is little-endian 32-bit MIPS, glibc 2.40, O32/NAN2008.
- Current Z-Mod toolchain family is `mipsel-buildroot-linux-gnu-*`.
- Display is `/dev/fb0`, 800x480 visible, 32 bpp, `jzfb`.
- Framebuffer virtual size is 800x960; page-flip behavior is not assumed until explicitly tested.
- Touch is a TSC2007 resistive device exposed through evdev. The `eventN` number is dynamic and must be discovered by device name.
- Do not depend on `/dev/uinput`; it is absent on the current AD5X kernel.
- Z-Mod owns screen handoff and process lifecycle. A future KlipperScreen integration should enter through that lifecycle rather than start independently over it.

## Stage 1 — toolchain ABI smoke

Current CI only proves the build path.

The workflow `.github/workflows/ad5x-display-spike.yml`:

1. checks out a pinned HelixScreen revision;
2. builds HelixScreen's AD5X Docker toolchain image;
3. compiles `ad5x_abi_smoke.c` with the MIPS32r5/O32/NAN2008 target flags used for the AD5X port;
4. records ELF headers, attributes, interpreter/program headers and compiler metadata;
5. publishes `ad5x-toolchain-smoke.tar.gz` as a GitHub Actions artifact.

The smoke binary is dynamically linked on purpose. Running it later inside the Z-Mod chroot will verify that the produced ELF and loader/libc ABI actually match the live printer instead of merely proving that the cross-compiler can emit a MIPS file.

## Stage 2 — minimal X11 display bundle

After Stage 1 runs successfully on hardware, build the smallest practical X11 runtime for AD5X:

- Xorg server;
- framebuffer video path (`fbdev` first; test `fbturbo` only if useful/necessary);
- `xf86-input-evdev`;
- fonts needed for a basic client;
- a tiny X11 test client;
- AD5X-specific Xorg config using `/dev/fb0` and touch-device discovery by evdev name.

Mesa/GLX is deliberately not a Stage 2 requirement. The AD5M reference image includes it, but that does not prove GTK3 needs it on AD5X.

## Stage 3 — GTK3 and KlipperScreen

Only after Xorg and touch are proven:

- GTK3 / GDK3;
- Cairo, Pango, fontconfig, gdk-pixbuf and their native dependencies;
- GObject Introspection / PyGObject matching the Z-Mod Python 3.12 runtime;
- upstream KlipperScreen connected to local Moonraker;
- RAM/CPU measurements before any permanent integration.

The final integration target, if the spike succeeds, is a Z-Mod-compatible `S80klipperscreen` path and a third display selection branch alongside GuppyScreen and HelixScreen. That change is intentionally out of scope for this spike.

## Safety rule

CI artifacts are test payloads, not installers. Do not patch `zdisplay.sh`, `S80guppyscreen`, stable plugin runtime, or Z-Mod files as part of the build spike.
