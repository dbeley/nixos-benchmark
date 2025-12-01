{
  description = "NixOS benchmark suite (flakes-based dev shell and runner)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        benchmarkTools = with pkgs; [
          p7zip
          tinymembench
          clpeak
          zstd
          pigz
          cryptsetup
          stress-ng
          fio
          ioping
          glmark2
          vkmark
          openssl
          netperf
          ffmpeg
          x264
          sqlite
          php
          gnumake
          sysbench
          python3
        ];

        runner = pkgs.writeShellApplication {
          name = "nixos-benchmark";
          runtimeInputs = benchmarkTools;
          text = ''
            python -m nixos_benchmark "$@"
          '';
        };
      in
      {
        packages.default = runner;
        apps.default = {
          type = "app";
          program = "${runner}/bin/nixos-benchmark";
        };
        devShells.default = pkgs.mkShell {
          packages = benchmarkTools ++ (with pkgs; [
            # Pre-commit and linting tools
            prek
            ruff
            typos
            python3Packages.mypy
            # Additional formatting and checking tools
            nixpkgs-fmt
          ]);
        };
      });
}
