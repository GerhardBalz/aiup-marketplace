# Source from the repository root to discover Marketplace catalog plugins.
# The fork's standalone issue workflow prototype is outside the catalog.
catalog_plugin_dirs=()
for catalog_dir in aiup-*/; do
  if [ -d "$catalog_dir" ] && [ "$catalog_dir" != aiup-issue-workflow/ ]; then
    catalog_plugin_dirs+=("$catalog_dir")
  fi
done
unset catalog_dir
