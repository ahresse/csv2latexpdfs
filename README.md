csv2latexpdfs.py
==============

Uses a LaTeX template to generate a bunch of PDF files using substitutions
stored in a CSV file or specified on the command line.

## Key Features

* Template-driven PDF generation using LaTeX with Jinja2 templating
* Batch processing from CSV files or single generation from command-line
* Custom syntax designed to work seamlessly with LaTeX
* Flexible output control with configurable filenames
    
## How to use

1. Build a LaTeX template using modified Jinja syntax (so that it
plays nicely with LaTeX syntax). The syntax changes are as follows:

* `\VAR{foo}` specifies a variable called `foo`.
* `\BLOCK{}` defines a block of Jinja template code.
* `\#{}` defines a comment; `%#` turns the whole line into a comment
* Refer to the Jinja docs at http://jinja.pocoo.org/docs/ for more info.

2. Create a CSV file containing the variable to make in the LaTeX template.
Each row in the CSV file will produce one PDF:
* For every variable named `foo`, there should be a corresponding substitution
column in the CSV file.
* The first row of the CSV file should contain the names of all the variables
in the template file (e.g. if the template has variables `\VAR{FullName}` and
`\VAR{Address}`: the CSV file's first row should have columns titled FullName
and Address).
* There is no specific order to respect for these names.
* Include a column called output_file to specifies the output PDF filename.
* Each CSV's row contains the variable substitutions for one single PDF.

3. Run the code as follows:

		$ ./csv2latexpdfs.py <template-file.tex> <substitutions-file.csv>

* Alternative usage:
 Specify the fields directly on the command line using `key=value` syntax.
(only works for generating one PDF)

		$ ./csv2latexpdfs.py <template-file.tex> <key1=val1> <key2=val2> ...

## Usage

$ csv2latexpdfs.py [-h] [-o OUTPUT] [-v] template [substitutions]

Generate PDF files from LaTeX templates using jinja2

positional arguments:
  template              LaTeX template file with jinja2 syntax
  substitutions         Input file with substitutions (CSV or key=value format). Use "output_file" key to specify destination for each PDF (default: None)

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Directory to output PDF (default: None)
  -v, --verbose         Show detailed processing information (default: False)
  
## System Requirements

* Python 3.8+
* LaTeX distribution (pdflatex)
* Jinja2

## License

MIT License - See LICENSE for details.
