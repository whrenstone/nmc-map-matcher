"""
arcgiscsv_report.py outputs VISTA table files in the current directory for an ArcGIS CSV
    GPS track
@author: Kenneth Perrine
@contact: kperrine@utexas.edu
@organization: Network Modeling Center, Center for Transportation Research,
    Cockrell School of Engineering, The University of Texas at Austin 
@version: 1.0

@copyright: (C) 2014, The University of Texas at Austin
@license: GPL v3

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
from __future__ import print_function
from datetime import datetime
from nmc_mm_lib import vista_network, path_engine, gtfs, compat
import sys, arcgiscsv_extracted, transit_gtfs, problem_report

# TODO: This is not used:
def arcgiscsvReport(gtfsNodes, vistaGraph, outFile = sys.stdout):
    """
    Takes a node set and outputs VISTA table files that report the link matches for the ArcGIS CSV GPS track set.
    @type gtfsNodes: list<path_engine.PathEnd>
    @type vistaGraph: graph.GraphLib  
    """
    print("objID,datafileID,linkID,time,restart,lat,lng,vistaLat,vistaLng", file = outFile)

    datafileIDs = compat.listkeys(gtfsNodes)
    datafileIDs.sort()
    for datafileID in datafileIDs:
        gtfsNodeList = gtfsNodes[datafileID]
        "@type gtfsNodeList: list<path_engine.PathEnd>"
        for node in gtfsNodeList:
            "@type node: path_engine.PathEnd"
            
            if len(node.routeInfo) > 0:
                (vistaLat, vistaLng) = vistaGraph.GPS.feet2gps(node.pointOnLink.pointX, node.pointOnLink.pointY) 

                for link in node.routeInfo:            
                    outStr = "%d,%s,%d,%s,%d,%g,%g,%g,%g" % (node.shapeEntry.shapeSeq, node.shapeEntry.shapeID, link.id,
                                node.shapeEntry.time.strftime('%m/%d/%Y %H:%M:%S'), 1 if node.restart else 0, node.shapeEntry.lat,
                                node.shapeEntry.lng, vistaLat, vistaLng)
                    print(outStr, file = outFile)

def syntax(retCode):
    """
    Print usage information
    """
    print("arcgiscsv_report outputs VISTA table files in the current directory for an ArcGIS CSV ")
    print("track.")
    print()
    print("Usage:")
    print("  python arcgiscsv_report.py dbServer network user password arcgiscsvFile arcgiscsvPathMatch")
    print("    [-p] [-s sourceID] -t refDateTime [-e endTime]")
    print()
    print("where:")
    print("  -p outputs a problem report (suppresses other output)")
    print("  -s is the sourceID to report in the travel_time output (0 by default)")
    print("  -t is the zero-reference time that all arrival time outputs are related to.")
    print("     (Note that the day is ignored.) Use the format HH:MM:SS.")
    print("  -e is the end time in seconds (86400 by default)")
    sys.exit(retCode)

def main(argv):
    # Initialize from command-line parameters:
    if len(argv) < 7:
        syntax(0)
    dbServer = argv[1]
    networkName = argv[2]
    userName = argv[3]
    password = argv[4]
    csvFilename = argv[5]
    csvPathMatch = argv[6]
    sourceID = 0
    endTime = 86400
    refTime = None
    problemReport = False
    
    if len(argv) > 6:
        i = 7
        while i < len(argv):
            if argv[i] == "-s" and i < len(argv) - 1:
                sourceID = int(argv[i + 1])
                i += 1
            elif argv[i] == "-t" and i < len(argv) - 1:
                refTime = datetime.strptime(argv[i + 1], '%H:%M:%S')
                i += 1
            elif argv[i] == "-e" and i < len(argv) - 1:
                endTime = int(argv[i + 1])
                i += 1
            elif argv[i] == "-p":
                problemReport = True
            i += 1
    
    if refTime is None and not problemReport:
        print("ERROR: No reference time is specified.")
        syntax(1)

    # Get the database connected:
    print("INFO: Connect to database...", file = sys.stderr)
    database = vista_network.connect(dbServer, userName, password, networkName)
    
    # Read in the topology from the VISTA database:
    print("INFO: Read topology from database...", file = sys.stderr)
    vistaGraph = vista_network.fillGraph(database)
    
    # Read in the GPS track information:
    print("INFO: Read ArcGIS CSV GPS track '%s'..." % csvFilename, file = sys.stderr)
    gpsTracks = arcgiscsv_extracted.fillFromFile(csvFilename, vistaGraph.gps)
    
    # Restore the path match:
    print("INFO: Read the ArcGIS CSV path-match file '%s'..." % csvPathMatch, file = sys.stderr)
    with open(csvPathMatch, 'r') as inFile:
        nodes = path_engine.readStandardDump(vistaGraph, gpsTracks, inFile, lambda x: str(x))

    # Assumption: Each shapeID corresponds with one trip that will be reported in the output.
    # And, each route corresponds with one trip.
    
    # Filter out nodes that have one or zero links:
    for shapeID in compat.listkeys(nodes):
        ctr = 0
        for node in nodes[shapeID]:
            ctr += len(node.routeInfo)
        if ctr <= 1:
            print("INFO: Filtering out shapeID %s." % str(shapeID), file = sys.stderr)
            del nodes[shapeID]
            del gpsTracks[shapeID]

    # Deal with Problem Report:
    if problemReport:
        print("INFO: Output problem report CSV...", file = sys.stderr)
        problem_report.problemReport(nodes, vistaGraph)
        print("INFO: Done.", file = sys.stderr)
        return

    # TODO: The logic below is a hack to create unique routes given GDB IDs.  There are several
    # long-term problems with this, including the idea that it is impossible to reuse common
    # routes (each instance is its own route) and there are assumptions about vehicle ID
    # numbering in the generated vehicles.
    
    # Fabricate routes:
    routes = {}
    ctr = 1 # We'll be making arbitrary route IDs:
    for shapeID in gpsTracks:
        routes[ctr] = gtfs.RoutesEntry(ctr, shapeID, "")
        ctr += 1

    # Let vehicle IDs be in a different number range: 
    vehCtr = int(ctr / 10000)
    vehCtr += 10000

    # Fabricate trips and stop times:
    trips = {}
    stopTimes = {}
    for routeID in routes:
        trips[vehCtr] = gtfs.TripsEntry(vehCtr, routes[routeID], "", gpsTracks[routes[routeID].shortName])
        stopTimes[trips[vehCtr]] = list() # Fake the system by having no stops defined.
        vehCtr += 1
    tripIDs = compat.listkeys(trips)
    tripIDs.sort()
       
    # Output the routes file:
    print("INFO: Dumping public.bus_route.csv...", file = sys.stderr)
    with open("public.bus_route.csv", 'w') as outFile:
        transit_gtfs.dumpBusRoutes(trips, userName, networkName, outFile)

    # Output the routes_link file:
    print("INFO: Dumping public.bus_route_link.csv...", file = sys.stderr)
    with open("public.bus_route_link.csv", 'w') as outFile:
        transit_gtfs.dumpBusRouteLinks(trips, stopTimes, nodes, vistaGraph, 1, False, userName, networkName, refTime, endTime,
            False, False, False, False, outFile)
    print("INFO: Dumping public.bus_frequency.csv...", file = sys.stderr)
    with open("public.bus_frequency.csv", 'w') as outFile:
        transit_gtfs._outHeader("public.bus_frequency", userName, networkName, outFile)
        print("\"route\",\"period\",\"frequency\",\"offsettime\",\"preemption\"", file = outFile)
        
        for tripID in tripIDs:
            departureTime = trips[tripID].shapeEntries[0].time
            timeDiff = departureTime - refTime
            print("%d,1,86400,%d,0" % (tripID, timeDiff.days * 24 * 3600 + timeDiff.seconds), file = outFile)

    print("INFO: Dumping public.bus_period.csv...", file = sys.stderr)
    with open("public.bus_period.csv", 'w') as outFile:
        transit_gtfs._outHeader("public.bus_period", userName, networkName, outFile)
        print("\"id\",\"starttime\",\"endtime\"", file = outFile)
        print("1,0,%d" % endTime, file = outFile)

    # Now we need to write out to the travel_time output:
    print("INFO: Dumping public.travel_time.csv...", file = sys.stderr)
    with open("public.travel_time.csv", 'w') as outFile:
        transit_gtfs._outHeader("public.travel_time", userName, networkName, outFile)
        print("\"departure_time\",\"vehicle_id\",\"route_id\",\"exittime\",\"linkid\",\"arrivaltime\",\"sourceid\"", file = outFile)
                                
        for tripID in tripIDs:
            nodeList = nodes[trips[tripID].route.shortName]
            "@type nodeList: list<path_engine.PathEnd>"
            departureTime = trips[tripID].shapeEntries[0].time
            lastTime = trips[tripID].shapeEntries[-1].time
            
            # Add the first link to the file:
            timeDiff = departureTime - refTime
            timeDiffLast = lastTime - refTime
            outStr = "%d,%d,%d,%d,%d,%d,%d" % (timeDiff.days * 24 * 3600 + timeDiff.seconds, trips[tripID].route.routeID,
                 tripID, timeDiffLast.days * 24 * 3600 + timeDiffLast.seconds, nodeList[0].pointOnLink.link.id,
                 timeDiff.days * 24 * 3600 + timeDiff.seconds, sourceID)            
            print(outStr, file = outFile)
            
            for node in nodeList:
                "@type node: path_engine.PathEnd"
                if len(node.routeInfo) > 0:
                    # TODO: Deal with midnight if the time is before refTime.
                    arrivalTime = node.shapeEntry.time
                    for link in node.routeInfo:
                        arrivalTimeSec = 3600 * arrivalTime.hour + 60 * arrivalTime.minute + arrivalTime.second
                        # TODO: We need to make vehicleID, routeID and tripID be consistent.
                        timeDiffArr = arrivalTime - refTime
                        outStr = "%d,%d,%d,%d,%d,%d,%d" % (timeDiff.days * 24 * 3600 + timeDiff.seconds,
                            trips[tripID].route.routeID, tripID, timeDiffLast.days * 24 * 3600 + timeDiffLast.seconds,
                            link.id, timeDiffArr.days * 24 * 3600 + timeDiffArr.seconds, sourceID)
                        print(outStr, file = outFile)

    print("INFO: Done.", file = sys.stderr)
    
# Boostrap:
if __name__ == '__main__':
    main(sys.argv)
