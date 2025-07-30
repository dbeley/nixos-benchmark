{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    phoronix-test-suite
    bison flex gmp libaio SDL2 zlib openssl
    python3 php nginx
  ];
}
