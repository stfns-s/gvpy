#!/usr/bin/env perl
# perl reference code: implements a subset of https://github.com/StanfordVLSI/Genesis2
use strict;
use warnings;
use FileHandle;
use File::Basename;
use Getopt::Long;

our $VERSION = "0.2.1";

# globals
my $prog     = basename($0);
my $comment  = "//";
my $PERL_ESC = "//;";
my $PERL_ESC2;
my $rawperl   = 0;
my $nobe     = 0;
my $mname    ;
my $help     = 0;
my $version  = 0;
my @libdirs  = ("./");
my @incdirs  = ("./");
my %defparams = ();
my $ExecPerl = "";

my %opts = (
    "help"       => \$help,
    "version|v"  => \$version,
    "libdirs=s"  => \@libdirs,
    "incdirs=s"  => \@incdirs,
    "defparam=s" => \%defparams,
    "pdebug"     => \$rawperl,
    "rawperl"    => \$rawperl,
    "mname=s"    => \$mname,
    "comment=s"  => \$comment
);

usage() and exit(1) if !GetOptions(%opts);
print "gvp $VERSION\n" and exit(0) if $version;
usage() and exit(0) if $help;


$PERL_ESC2 = "$comment" . ";" if $comment ne "//";
@libdirs = split(/,/, join(',', @libdirs));
@incdirs = split(/,/, join(',', @incdirs));

initPerl();
foreach my $f (@ARGV) { parseFile($f); }

if ($rawperl) {
	formatPerl($ExecPerl);
} else {
	my $r = eval $ExecPerl;

	if (defined $@ && $@ ne "") {
        my $err = $@; 
        printf STDERR "Error: $err";

		my $base = basename($ARGV[0] // "unknown");
		my $tmpfile = "/tmp/$base.$$\.pl";

        eval { unlink($tmpfile) };

		if (open my $fh, ">", $tmpfile) {
			print STDERR "\n$prog: dumping generated perl to $tmpfile..\n";
			print $fh $ExecPerl;
			close $fh;
			printf STDERR "$prog: running \"perl -w $tmpfile\" for debug info:\n%s\n", '-' x 80;
            system("perl", "-w", $tmpfile);
			printf STDERR "%s\n", '-' x 80;
		} else {
			print STDERR "$prog: error could not write $tmpfile\n";
		}
		exit 1;
	}
}

exit 0;

sub formatPerl {
    my $src = shift;
    my $have_perltidy = system("command -v perltidy >/dev/null 2>&1") == 0;
    if ($have_perltidy && open(my $fh, "|-", "perltidy -l 140 -sbl -ce -i=4 -ci=4")) {
        print $fh $src;
        close($fh) and return;
    }
    print STDERR "$prog: perltidy unavailable; emitting raw output\n";
    print $src;
}

sub usage {
    my $prog     = basename($0);
    print << "_EOH_";
usage: $prog [--h|--d] [-v] [--libdir dir] [--incdir dir] [--defparam param=val] file(s)
    --h              : This message
    -v, --version    : Show version and exit
    --rawperl|pdebug : Output tidyed up raw perl for debugging, rather than target language
    --mname  name    : Set top module name
    --libdir d1,d2,. : Add dirs to the lib path (perl INC path),
    --incdir d1,d2,. : Add dirs to the include search path (used by $comment; include("filename"))
    --defparam p=v   : Set parameter 'p' to value 'v'
    --comment str    : Set the comment start of output language to "str" (default "//"). 
                       Note that this also adds the gvp perl escape to "str"; (default "//;")

_EOH_
}

sub parseFile {
    my $fname = shift;
    my $incl  = shift;
    my $fh;

    if (defined $fname) {
        unless (defined($fh = FileHandle->new($fname, "r"))) {
            printf STDERR "ERROR: Could not open $fname for reading\n";
            exit 1;
        }
    } else {
        $fname = "STDIN";
        $fh    = \*STDIN;
    }

    $incl = 0 unless defined $incl;
    my $name = defined $mname ? $mname : (basename($fname, (".vp", ".gvp")));
    $ExecPerl .= "\$mname = \"$name\";\n" unless $incl;

    my $out = "";
    my $perl_mode = 0;
    my $ln = 0;

    while (my $line = <$fh>) {
        my $orig_line = $line;
        my $warn;

        $ln++;

        if ($line =~ m/^\s*\Q$PERL_ESC\E/ || (defined $PERL_ESC2 && $line =~ m/^\s*\Q$PERL_ESC2\E/)) {
            $line =~ s/^(\s*)\Q$PERL_ESC\E/$1/g;
            $line =~ s/^(\s*)\Q$PERL_ESC2\E/$1/g if defined $PERL_ESC2;

            if ($line =~ s/^\s*pinclude\s*\(\s*(['"])([^'"]+)\1\s*\)//) {
                pinclude($2);
            } elsif ($line =~ s/^\s*include\s*\(\s*(['"])([^'"]+)\1\s*\)//) {
                include($2);
            } else {
                $ExecPerl .= $line;
            }
        } else {
            chomp $line;
            $out = "emit(\'";
            $perl_mode = 0;

            if ($line =~ s/^(\s*\/?\/?)(\s*`)(timescale|default_nettype|include|ifdef|if|ifndef|else|endif)//) {
                $out .= $1 . $2 . $3 . " ";
            }

            for (my $i = 0; $i < length($line); $i++) {
                my $char = substr($line, $i, 1);
                my $next_char = ($i + 1 < length($line)) ? substr($line, $i + 1, 1) : '';

                if ($char . $next_char eq '\`') {
                    $out .= $next_char;
                    $i++;
                } elsif ($char eq "`") {
                    $out .= $perl_mode ? "); emit('" : "'); emit(";
                    $perl_mode = !$perl_mode;
                } else {
                    $char = "\\$char" if !$perl_mode && ($char eq "'" || $char eq "\\");
                    $out .= $char;
                }
            }

            $out .= $perl_mode ? ";\n" : "');";

            if ($perl_mode) {
                print STDERR "ERROR:: ($fname, $ln) Missing closing backtick:\n\t$orig_line";
                exit 1;
            }
            print STDERR "WARNING:: ($fname, $ln) $warn: \n\t$orig_line" if defined $warn;

            $ExecPerl .= $out . "emit \"\\n\";\n";
        }
    }

    return $ExecPerl;
}

sub include {
    my $fn = shift;

    if ($fn =~ /^\//) {
        $ExecPerl .= "emit \"$comment begin file: $fn\\n\";\n";
        parseFile($fn, 1);
        $ExecPerl .= "emit \"$comment end file: $fn\\n\";\n";
    } else {
        foreach my $dir (@incdirs) {
            my $ffn = "$dir/$fn";
            if (-f $ffn) {
                $ExecPerl .= "emit \"$comment begin file: $ffn\\n\";\n";
                parseFile($ffn, 1);
                $ExecPerl .= "emit \"$comment end file: $ffn\\n\";\n";
                return;
            }
        }
        printf STDERR "ERROR:: could not find file $fn in include path '%s'\n", join(':', @incdirs);
        exit 1;
    }
}

sub pinclude {
    my $fn = shift;

    if ($fn =~ /^\//) {
        $ExecPerl .= "emit \"$comment begin perl file: $fn\\n\";\n";
        $ExecPerl .= do { local (@ARGV, $/) = ($fn); <> };
        $ExecPerl .= "emit \"$comment end perl file: $fn\\n\";\n";
    } else {
        foreach my $dir (@incdirs) {
            my $ffn = "$dir/$fn";
            if (-f $ffn) {
                $ExecPerl .= "emit \"$comment begin perl file: $ffn\\n\";\n";
                $ExecPerl .= do { local (@ARGV, $/) = ($ffn); <> };
                $ExecPerl .= "emit \"$comment end perl file: $ffn\\n\";\n";
                return;
            }
        }
        printf STDERR "ERROR:: could not find file $fn for pinclude in '%s'\n", join(':', @incdirs);
        exit 1;
    }
}


sub initPerl {
    $ExecPerl .= "use strict;";
    foreach my $d (@libdirs) {
        $ExecPerl .= "use lib \"$d\";\n";
    }
    $ExecPerl .= "my %parameters = (\n";
    foreach my $p (keys %defparams) {
        (my $v = $defparams{$p}) =~ s/(['\\])/\\$1/g;
        $ExecPerl .= "\t$p\t=>\t'$v',\n";
    }
    $ExecPerl .= "\t);\n\n";
    $ExecPerl .= "my \$comment=\"$comment\";\n\n";

    $ExecPerl .= q{
# parameter stub 
sub parameter {
    my %argh = @_;
    my $name = "NAME";

    if (exists $argh{'name'}) { $name = $argh{'name'}; }

    if (exists $parameters{$name}) {
        print "$comment parameter $name => $parameters{$name} (command line)\n";
        return $parameters{$name};
    }
    if (exists $argh{'val'}) {
        print "$comment parameter $name => $argh{'val'} (default value)\n";
        return $argh{'val'};
    } else {
        print "$comment parameter $name => UNDEFINED\n";
        return undef;
    }
}

my $mname = "FIXME";
sub mname { return $mname }

sub pp {
    my $num = shift;
    my $fmt = shift;
    $fmt = "%02d" unless defined $fmt;
    return sprintf $fmt, $num;
}

sub emit { print @_; }

my $self = {};
bless $self;

sub generate {
    my $arg1 = shift;
    my $tname = ref($arg1) eq ref($main::self) ? $arg1 : shift;
    my $iname = shift;
    my %argh = @_;

    $self->{$tname}->{$iname}->{'tname'} = $tname;
    $self->{$tname}->{$iname}->{'iname'} = $iname;
    %{$self->{$tname}->{$iname}->{'params'}} = %argh;

    return bless $self->{$tname}->{$iname};
}

sub generate_base { generate(@_); }

sub instantiate {
    my $i = shift;

    emit "$i->{'tname'} /*PARAMS: ";
    my %params = %{$i->{'params'}};
    foreach my $k (keys %params) {
        emit "$k=>"; emit $params{$k}; emit " ";
    }
    emit " */ $i->{'iname'}";
}

sub synonym { }
};
}
