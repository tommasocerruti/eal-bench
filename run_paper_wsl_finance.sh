cd /mnt/c/Users/mikad/Documents/GitHub/eal-bench || exit 1
until grep -q "PAPER ROUTES DONE (cybersecurity)" results/extensions_driver.log; do sleep 60; done
bash run_paper_wsl.sh results/extensions_driver.log finance