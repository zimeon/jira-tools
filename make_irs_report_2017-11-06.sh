/story_feature_policy_report.py
cat irs_report.tex | perl -pe 's/Critical/Essential/g; s/Access & Delivery/Access \\& Delivery/g' > irs_report_2017-11-06.tex
pdflatex irs_report_2017-11-06
pdflatex irs_report_2017-11-06