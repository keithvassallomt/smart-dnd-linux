# Releasing

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds every package, publishes a
GitHub release, and updates the AUR. FriendlyHub is updated by pull request.

---

## Cutting a release

1. Bump the version in three places:
   - `pyproject.toml` (`version`)
   - `smart_dnd/__init__.py` (`__version__`)
   - `data/com.keithvassallo.SmartDnd.metainfo.xml`: add a new `<release>` **at the top** of
     `<releases>`, with a date and a short description. FriendlyHub reads the version from it.
2. Check them, including the tag you're about to push:
   ```bash
   just check-version v0.2.0
   ```
3. Optionally do a dry run of the whole pipeline on GitHub first (see below).
4. Commit, tag and push:
   ```bash
   git tag v0.2.0
   git push origin main v0.2.0
   ```

The deb, rpm and AUR versions are set from the tag at build time; their files in `packaging/` don't
need bumping.

## What the workflow does

| Job | Output |
|---|---|
| Check version | Fails if the version strings disagree with each other or the tag |
| Wheel and sdist | `smart_dnd_linux-X-py3-none-any.whl`, `smart_dnd_linux-X.tar.gz` |
| Debian / Ubuntu | `smart-dnd_X-1_all.deb`, installed and smoke-tested on Ubuntu |
| Fedora | `smart-dnd-X-1.fcNN.noarch.rpm`, installed and smoke-tested on Fedora |
| Flatpak | `smart-dnd-X-x86_64.flatpak` (GNOME runtime) |
| FriendlyHub files | `com.keithvassallo.SmartDnd.yaml` (pointing at the tag) and the metainfo |
| GitHub release | All of the above plus `SHA256SUMS`, with generated release notes |
| AUR | Builds the `smart-dnd` PKGBUILD, then pushes `PKGBUILD` and `.SRCINFO` to the AUR |

The AUR job only runs after the GitHub release succeeds, so a failed build never reaches the AUR.

## Dry runs

```bash
just release-dry-run          # or: gh workflow run release.yml --ref <branch>
```

A dry run (manual `workflow_dispatch`) runs every build and test, including the AUR package build
from the current checkout, but creates no release and pushes nothing to the AUR.

## One-time setup: AUR publishing

The workflow pushes to `ssh://aur@aur.archlinux.org/smart-dnd.git` using an SSH key stored as the
`AUR_SSH_PRIVATE_KEY` repository secret. Use a key made only for this, not your personal one: a
secret can leak through a compromised Action, and a CI key can't have a passphrase. Your AUR account
accepts several public keys, so the new one sits next to your existing key.

1. Create the key:
   ```bash
   ssh-keygen -t ed25519 -N "" -C "smart-dnd-linux release CI" -f ~/.ssh/aur_smart_dnd_ci
   ```
2. On the AUR, open **My Account**, add the contents of `~/.ssh/aur_smart_dnd_ci.pub` as a **new
   line** in **SSH Public Key** (keep your existing key), enter your password and **Update**.
3. Check the AUR accepts it. This should print the AUR's list of commands:
   ```bash
   ssh -i ~/.ssh/aur_smart_dnd_ci -o IdentitiesOnly=yes aur@aur.archlinux.org help
   ```
4. Store the private key as the secret, then delete the local copy:
   ```bash
   gh secret set AUR_SSH_PRIVATE_KEY -R keithvassallomt/smart-dnd-linux < ~/.ssh/aur_smart_dnd_ci
   rm ~/.ssh/aur_smart_dnd_ci
   ```

The first release creates the `smart-dnd` package on the AUR. To revoke CI's access, delete its line
from your AUR SSH keys. `smart-dnd-git` (in `packaging/aur/smart-dnd-git/`) tracks `main` and isn't
touched by releases; push it to the AUR by hand when its PKGBUILD changes.

## FriendlyHub

FriendlyHub builds the Flatpak itself (x86_64 and aarch64) from the manifest and metainfo attached
to each GitHub release.

- **First submission:** fork [friendlyhub/submissions](https://github.com/friendlyhub/submissions),
  add a `com.keithvassallo.SmartDnd/` directory containing the release's
  `com.keithvassallo.SmartDnd.yaml` and `com.keithvassallo.SmartDnd.metainfo.xml`, and open a PR.
  Verifying the `keithvassallo.com` domain is optional; see the FriendlyHub docs.
- **Updates:** open a PR to `friendlyhub/com.keithvassallo.SmartDnd` replacing those two files
  with the new release's copies.

The in-repo manifest builds from the working tree (`type: dir`) so it can be built locally with
`just build-flatpak`. `packaging/flatpak/friendlyhub-manifest.py` produces the tag-based version.

### Updating the Flatpak's bundled dependencies

The manifest pins libical and Evolution Data Server (not in the GNOME runtime) and the `hatchling`
wheels used to build Smart DND. When bumping the runtime version, check
[GNOME Calendar's Flathub manifest](https://github.com/flathub/org.gnome.Calendar), which builds the
same libical and EDS against each GNOME runtime, and update the URLs and `sha256` values to match.
