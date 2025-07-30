{ pkgs ? import <nixpkgs> {} }:

let
  pythonPackages = pkgs.python3Packages;
in pkgs.mkShell {
  buildInputs = with pkgs; [
    phoronix-test-suite
    p7zip
    bison flex gmp libaio SDL2 zlib openssl
    php
    python3
    yasm
    pythonPackages.pip
    pythonPackages.distutils
    pythonPackages.pyyaml
    pythonPackages.numpy
    pythonPackages.cython
    pythonPackages.ninja
    pythonPackages.cmake
  ];
}
