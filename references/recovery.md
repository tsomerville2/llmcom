# Keeping an upstream emergency copy

Vendoring means distributing dependency source or artifacts alongside your own project. A repository can contain a `rescue/` directory and a Python wheel/sdist can include those files as package data. A package registry does not automatically copy an upstream Git repository referenced by your project.

LLMCom 0.1.0 includes its integration code, skills and pinned npm lockfile. It does **not** include a vendored upstream recovery archive or an offline restore command. Normal setup downloads the pinned upstream dependencies and Node runtime.

A future explicit rescue bundle should contain:

- Source mirrors or Git bundles for upstream projects, with exact commits and licenses.
- Registry tarballs for every dependency in the npm lockfile, including transitive dependencies, verified against the lockfile integrity hashes.
- The appropriate Node runtime archives and separately downloaded native binaries or build prerequisites for each supported architecture.
- The LLMCom wheel/sdist, dependency manifest, checksums and instructions.
- A restore process tested with network access disabled on a fresh supported machine.

Source alone is insufficient for rebuilding a native dependency when its toolchain or binary downloads have disappeared. An offline dependency registry or complete npm cache can complement archived tarballs, but it must be tested rather than assumed complete. Backing up Claude/Codex client code does not preserve access to their hosted model services.

Keep ordinary installs pointed at upstream. Emergency restore should be a deliberate separate command, pinned to the archived release, rather than silently switching to an older copy when an online installation fails. Preserve third-party licenses and notices when distributing vendored files.

An embedded rescue archive can be committed to GitHub and shipped as package data on PyPI. Large bundles may be better as separate release assets or an optional rescue distribution. Store an additional copy outside GitHub/PyPI, such as an external drive and independent object storage.

Useful references: [GitHub repository backup](https://docs.github.com/en/repositories/archiving-a-github-repository/backing-up-a-repository), [GitHub mirroring](https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository), [npm package archives](https://docs.npmjs.com/cli/v11/commands/npm-pack/), [npm lockfile format](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/).
