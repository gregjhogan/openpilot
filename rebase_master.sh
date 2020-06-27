#!/bin/bash -e

cd "$(dirname "$0")"

submodules=(
cereal
opendbc
panda
)

echo -e "\e[34m[UPDATING openpilot]\e[0m"
if [ "$INIT" == "1" ]; then
  git remote add upstream https://github.com/commaai/openpilot
fi
git fetch upstream master
git checkout master
git rebase upstream/master
git push --force-with-lease

for submodule in ${submodules[@]}; do
  echo -e "\e[34m[UPDATING $submodule]\e[0m"
  pushd "$submodule"
  if [ "$INIT" == "1" ]; then
    git remote add upstream "https://github.com/commaai/$submodule"
  fi
  git fetch upstream master
  git checkout master
  git rebase upstream/master
  git push --force-with-lease
  popd
done

echo -e "\e[34m[SUBMODULE RESET]\e[0m"
git submodule update
