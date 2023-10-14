this needs some serious adjustment...

insert the addresses into the tsv file

addressLine,postalCode,locality,countryRegion,goodsDemand,comment

run main.py with a command line argument 
    
    python main.py -f addresses.tsv

then it will give you a matrix of distances

you then have input that into the ORtools.py program.  (this section needs to be reworked)
 it will then output the order to go 

then input these address into google maps and you can send to email which will create a link

*** future ideas I think the matrix should be outputed directly into the ORtools program or those two combined 
and then output the address in order***

try running 
python travelingSalesman.py -f addresses.tsv
