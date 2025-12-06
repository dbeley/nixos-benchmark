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
        src = pkgs.lib.cleanSource ./.;

        benchmarkTools = with pkgs; [
          p7zip
          tinymembench
          clpeak
          lz4
          zstd
          pigz
          cryptsetup
          stress-ng
          stockfish
          fio
          ioping
          glmark2
          vkmark
          furmark
          openssl
          x265
          john
          hashcat
          netperf
          wrk
          stressapptest
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
            export NIXPKGS_ALLOW_UNFREE=1
            export PYTHONPATH="${src}:$PYTHONPATH"
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
            python3Packages.flake8
            typos
            python3Packages.mypy
            # Additional formatting and checking tools
            nixpkgs-fmt
          ]);
          shellHook = ''
            export NIXPKGS_ALLOW_UNFREE=1
          '';
        };
      });
}
