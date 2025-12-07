#!/usr/bin/env bash
# my own script to share results between computers
rsync -azvhP --stats --no-t --inplace --zc=zstd --update --delete-after --zl=3 --checksum results/*.json ~/Nextcloud/30-39_Programmation/Projets/nixos-benchmark/
