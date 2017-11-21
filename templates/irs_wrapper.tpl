\documentclass[11pt]{{article}}
\renewcommand{{\familydefault}}{{\sfdefault}}
\usepackage{{helvet}}
%\usepackage{{times}}
\usepackage[pdftitle={{Samvera IR Evaluation - Feature, Policy, Story Appendix}},colorlinks=false,urlbordercolor={{0.9 0.9 0.9}},citebordercolor={{0.9 0.9 0.9}},linkbordercolor={{0.9 0.9 0.9}}]{{hyperref}}
\urlstyle{{sf}}

\setlength{{\parindent}}{{0mm}}
\setlength{{\parskip}}{{2mm}}
\setlength{{\textwidth}}{{6.5in}}
\setlength{{\textheight}}{{9.0in}}
\setlength{{\oddsidemargin}}{{0.0in}}
\setlength{{\topmargin}}{{-1.2cm}}

\begin{{document}}

\section*{{Samvera Evaluation}}

\section*{{Appendix 1. - A comparison of current bepress and DSpace IR features list (generated from the IR user stories work) mapped to current status of Samvera/Hyrax development}}

\textit{{{date}}}

Summary report of features and policies needed to support the institutional
repository (IR) user stories first identified by the 
\href{{https://confluence.cornell.edu/x/MzF0Ew}}{{IR User Stories Working Group 2015}}
and subsequently updated for the Samvera IR Evaluation 2017.
This report is intended as a resource to help guide the continuing 
development of a Samvera/Hyrax based IR solution within Cornell
University Library.

\setcounter{{tocdepth}}{{2}}
\tableofcontents

\clearpage
\section{{Methodology}}

Each user story was interrogated to determine which features and policies
would be necessary to support that user story. This method resulted in a
list of features and policies, which were then prioritized as 
\textbf{{Critical}}, \textbf{{Major}}, or \textbf{{Low}}, using the
following criteria:

\begin{{itemize}} 
\item \textbf{{Critical}} - This feature is a core function of the repository,
absolutely necessary for its operation. Reasons a feature is
considered \textbf{{Critical}} include but are not limited to:
\begin{{itemize}}
\item relied upon by existing eCommons DSpace, DC@ILR DigitalCommons@ILR, and/or
SHA Scholarly Commons repositories
\item many user stories rely on the feature
\item funding or institutional obligations depend on the feature
\item a significant minority of users rely on the feature
\item repository experts aver that it is necessary
\item stakeholder buy-in depends on the feature
\end{{itemize}}
\item \textbf{{Major}} - While this feature is not necessary for the repository
to function, it is considered important to its operation and use.
Reasons a feature is considered \textbf{{Major}} include but are not limited to:
\begin{{itemize}}
\item a fair number of user stories rely on this feature
\item a small but involved constituency of users prioritizes this feature
\item potential stakeholder buy-in or funding opportunities may arise if this feature is implemented
\end{{itemize}}
\item \textbf{{Low}} - This feature would be good to have, but is
nonessential. Reasons a feature is considered \textbf{{Low}} include but are
not limited to:
\begin{{itemize}}
\item only a small segment of users rely on this feature
\item considered to be a niche or tangential repository function
\end{{itemize}} 
\end{{itemize}} 

This prioritization allowed us the determine an inferred priority for 
each user story: the lowest of the priorities of the features and 
policies that it relies on. This allowed refinement of the features and 
policies list, and their associated priorities.

\clearpage
\section{{Features grouped by priority}}

{features}

\clearpage
\section{{Policies grouped by priority}}

{policies}

\clearpage
\section{{User stories}}

{user_stories}

\end{{document}}
