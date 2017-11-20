#!/bin/sh
report_name="irs_report_$1"
echo "Creating report $report_name..."
./story_feature_policy_report.py
cat irs_report.tex | perl -pe 's/Critical/Essential/g; s/Access & Delivery/Access \\& Delivery/g' > "$report_name.tex"
pdflatex $report_name
pdflatex $report_name
