# Releasing

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds every package, publishes a
GitHub release, and updates the AUR. FriendlyHub is updated by pull request.

---

## Cutting a release

As you work, add user-facing changes under `[Unreleased]` in `CHANGELOG.md`, in the
[Keep a Changelog](https://keepachangelog.com) categories (Added, Changed, Deprecated, Removed,
Fixed, Security). Then, from a clean `main`:

```bash
just release
```

It runs these steps, and changes nothing until the checks in step 1 pass:

1. **Checks**: on `main`, nothing uncommitted, not behind `origin/main`, `origin` is pushable, the
   `AUR_SSH_PRIVATE_KEY` secret exists, and the tests pass.
2. **Version and changelog** (`just bump-version`): if the current version is already tagged, it
   bumps from the last tag by what `[Unreleased]` contains: **patch** for Fixed/Security only,
   **minor** for Added/Changed/Deprecated/Removed, **major** for Removed after 1.0. It moves
   `[Unreleased]` into a `## [X.Y.Z] - today` section, regenerates the compare links, and updates
   `pyproject.toml`, `smart_dnd/__init__.py` and the metainfo `<release>` notes to match.
3. **Confirm**: shows the release notes and the files changed, then asks. Answering no restores
   every file.
4. **Publish**: commits `Release vX.Y.Z`, tags `vX.Y.Z`, and pushes both, which starts the release
   workflow. It waits for the workflow to finish (the Flatpak build takes the longest).
5. **FriendlyHub**: downloads `com.keithvassallo.SmartDnd.yaml` and `.metainfo.xml` from the
   release into `~/Downloads` (or `just release --friendlyhub-dir <dir>`).

The metainfo `<release>` notes are what FriendlyHub and software centres show as "What's new". By
default they're generated from the changelog section. To ship hand-written notes instead, write
the `<release>` entry yourself and run `just release --keep-metainfo-notes`: the description is
kept and only its date is updated. The first release, 0.1.0, uses this for a short non-technical
summary in place of the full feature list.

For a breaking change the inference can't see, bump explicitly first: `just bump-version major`
(or `minor`, `patch`, `X.Y.Z`), commit, then `just release`, which keeps a version that isn't
tagged yet. `just bump-version` on its own only edits files; it never commits.

The GitHub release notes are that version's `CHANGELOG.md` section, an install guide, and GitHub's
"Full Changelog" link. The deb, rpm and AUR versions are set from the tag at build time; their
files in `packaging/` don't need bumping.

### If the release workflow fails

The tag is already pushed by then. For a flaky job, rerun it:
`gh run rerun <run-id> --failed`. To fix something and release the same version again, delete the
tag, fix and commit, then run `just release` again; it reuses the untagged version:

```bash
git push origin --delete vX.Y.Z && git tag -d vX.Y.Z
```

If the GitHub release was already created, delete it first with `gh release delete vX.Y.Z`. The AUR
job runs last, so a failure before it never reaches the AUR.

If only the AUR job failed, the GitHub release is fine; leave it. Rerunning the failed job reuses
the workflow from the tagged commit, so if the fix is in the workflow, push it to `main` and publish
with the AUR workflow on its own instead:

```bash
gh workflow run aur.yml -f version=X.Y.Z
```

## What the workflow does

| Job | Output |
|---|---|
| Check version | Fails if the version strings disagree with each other or the tag, or `CHANGELOG.md` has no section for it |
| Wheel and sdist | `smart_dnd_linux-X-py3-none-any.whl`, `smart_dnd_linux-X.tar.gz` |
| Debian / Ubuntu | `smart-dnd_X-1_all.deb`, installed and smoke-tested on Ubuntu |
| Fedora | `smart-dnd-X-1.fcNN.noarch.rpm`, installed and smoke-tested on Fedora |
| Flatpak | `smart-dnd-X-x86_64.flatpak` (GNOME runtime) |
| FriendlyHub files | `com.keithvassallo.SmartDnd.yaml` (pointing at the tag) and the metainfo |
| GitHub release | All of the above plus `SHA256SUMS`; notes from `CHANGELOG.md` |
| AUR (`aur.yml`) | Builds the `smart-dnd` PKGBUILD, then pushes `PKGBUILD` and `.SRCINFO` to the AUR |

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
