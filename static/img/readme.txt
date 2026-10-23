The images in this tree are tracked in git, alongside the posts that use
them. A fresh clone has everything needed to build the site:

    git pull && hugo

This was not always so. These files used to live outside the repo, synced
between machines by Dropbox, with static/img listed in .gitignore. A machine
holding an incomplete copy would build a public/ missing images, and the
publish step

    rsync -avz --delete -e ssh public/* flaviof.com:flaviof.com/blog2/

would then delete those images from the live server. That happened, which is
why they are committed now.

Two things worth knowing when adding images here:

  - Reference them from a post as img/<dir>/<file>. The built pages carry
    <base href="https://www.flaviof.com/blog2/">, so that resolves to
    /blog2/img/<dir>/<file>.

  - macOS leaves resource-fork droppings (._* files and .DS_Store) in this
    tree. They are gitignored, and config.toml excludes them at the static
    mount, so they reach neither public/ nor the live server.

  - Strip the metadata before committing:

        python3 tools/strip-image-metadata.py static/img
        python3 tools/strip-image-metadata.py --check static/img

    Photos arrive from phones and photo editors carrying EXIF GPS positions,
    capture timestamps, camera and lens models, and editor provenance. This
    tree is published verbatim, so whatever is in a file goes to the web.
    about/scuba.jpg reached the repo with the GPS position of the dive site;
    a picture captioned "trails near home" would publish a home address the
    same way.

    Do not assume `sips -Z` has cleaned a file. It strips inconsistently --
    it flattened ten of the about photos and left the eleventh almost
    untouched. The tool rewrites only the container, so the compressed image
    data is copied through byte for byte: no re-encoding, no quality loss.
    --check changes nothing and exits non-zero if anything is left, so it
    also works as a pre-commit guard.

    SVG and PDF are reported, never rewritten. Review those by hand.
