{ pkgs ? import <nixpkgs> {
    config = {
      allowUnfree = true;
    };
  } }:

let
  pythonPackages = pkgs.python3Packages;
in pkgs.mkShell {
  buildInputs = with pkgs; [
    p7zip
    stress-ng
    fio
    glmark2
    openssl
    speedtest-cli
    ffmpeg
    x264
    sqlite
    php
    gnumake
    unigine-heaven
    unigine-valley
  ];
  shellHook = ''
    export NIXPKGS_ALLOW_UNFREE=1
  '';
}
