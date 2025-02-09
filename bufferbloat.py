#!/usr/bin/python
"CS244 Spring 2015 Assignment 1: Bufferbloat"

from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI
from mininet.clean import cleanup

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

from monitor import monitor_qlen
# import termcolor as T

import sys
import os
import math
import helper

# TODO: Don't just read the TODO sections in this code.  Remember that
# one of the goals of this assignment is for you to learn how to use
# Mininet. :-)

parser = ArgumentParser(description="Bufferbloat tests")
parser.add_argument('--bw-host', '-B',
                    type=float,
                    help="Bandwidth of host links (Mb/s)",
                    default=1000)

parser.add_argument('--bw-net', '-b',
                    type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)",
                    required=True)

parser.add_argument('--delay',
                    type=float,
                    help="Link propagation delay (ms)",
                    required=True)

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    required=True)

parser.add_argument('--time', '-t',
                    help="Duration (sec) to run the experiment",
                    type=int,
                    default=10)

parser.add_argument('--maxq',
                    type=int,
                    help="Max buffer size of network interface in packets",
                    default=100)

# Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
# behaviour.  For those who are curious, invoke this script with
# --cong cubic and see what happens...
# sysctl -a | grep cong should list some interesting parameters.
parser.add_argument('--cong',
                    help="Congestion control algorithm to use",
                    default="reno")

# Expt parameters
args = parser.parse_args()


class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."

    def build(self, n=2):
        # Here are two hosts
        hosts = []
        for i in range(1, n + 1):
            hosts.append(self.addHost('h%d' % (i)))

        # Here I have created a switch.  If you change its name, its
        # interface names will change from s0-eth1 to newname-eth1.
        switch = self.addSwitch('s0')

        # TODO: Add links with appropriate characteristics
        # get the link propagation delay (ms) and max queue size from args
        delay = '%sms' % args.delay
        max_queue = args.maxq
        # add link between h1 and switch
        self.addLink(hosts[0], switch, bw=args.bw_host, delay=delay, max_queue_size=max_queue)
        # add link between switch and h2
        self.addLink(switch, hosts[1], bw=args.bw_net, delay=delay, max_queue_size=max_queue)

        return


# Simple wrappers around monitoring utilities.  You are welcome to
# contribute neatly written (using classes) monitoring scripts for
# Mininet!

# tcp_probe is a kernel module which records cwnd over time. In linux >= 4.16
# it has been replaced by the tcp:tcp_probe kernel tracepoint.
def start_tcpprobe(outfile="cwnd.txt"):
    os.system("rmmod tcp_probe; modprobe tcp_probe full=1;")
    Popen("cat /proc/net/tcpprobe > %s/%s" % (args.dir, outfile),
          shell=True)


def stop_tcpprobe():
    Popen("killall -9 cat", shell=True).wait()


def start_qmon(iface, interval_sec=0.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor


def start_iperf(net):
    h2 = net.get('h2')
    print("Starting iperf server...")
    # For those who are curious about the -w 16m parameter, it ensures
    # that the TCP flow is not receiver window limited.  If it is,
    # there is a chance that the router buffer may not get filled up.
    server = h2.popen("iperf -s -w 16m")
    # TODO: Start the iperf client on h1.  Ensure that you create a
    # long lived TCP flow. You may need to redirect iperf's stdout to avoid blocking.
    h1 = net.get('h1')
    duration = args.time
    command = "iperf -c %s -t %s" % (h2.IP(), duration)
    print("Starting iperf client and tcp flow for %ss" % duration)
    client = h1.popen(command)


def start_webserver(net):
    h1 = net.get('h1')
    proc = h1.popen("python http/webserver.py", shell=True)
    sleep(1)
    return [proc]


def start_ping(net):
    # TODO: Start a ping train from h1 to h2 (or h2 to h1, does it
    # matter?)  Measure RTTs every 0.1 second.  Read the ping man page
    # to see how to do this.

    # Hint: Use host.popen(cmd, shell=True).  If you pass shell=True
    # to popen, you can redirect cmd's output using shell syntax.
    # i.e. ping ... > /path/to/ping.txt
    # Note that if the command prints out a lot of text to stdout, it will block
    # until stdout is read. You can avoid this by runnning popen.communicate() or
    # redirecting stdout

    print "Ping from h1 to h2, 10 pings per second"
    h1 = net.get('h1')
    h2 = net.get('h2')
    duration = args.time
    # Send 10 pings per second from h1 to h2
    # first %s parameter: The number of ping packets should be 10 times of the duration(interval time -i should be 0.1)
    # second %s parameter: The ip address of the destination(IP of h2)
    # third %s parameter: The directory to store outputs(args.dir)
    command = "ping -c %s -i 0.1 %s > %s/ping.txt" % (duration * 10, h2.IP(), args.dir)
    h1.popen(command, shell=True)


def measure_fetch_time(h1, h2):
    "Use curl command to download the page and measure how long it takes to fetch"
    # get the time point we send the fetch request
    fetch_clock = time()

    # communicate() returns a tuple (stdoutdata, stderrdata)
    # communicate()[0] is used to access the stdoutdata and communicate()[1] to access the stderrdata
    # to get the total time we use to fetch the html we use communicate()[0]
    fetch_time = h2.popen("curl -o /dev/null -s -w %%{time_total} %s/http/index.html" % h1.IP(), shell=True).communicate()[0]
    fetch_info = [fetch_clock, float(fetch_time)]
    return fetch_info


def save_download_time_to_file(measure_data):
    "Save the time point and download time to download.txt"
    with open(args.dir + "/download.txt", "w") as f:
        for i in measure_data:
            i = str(i).strip('[').strip(']') + '\n'
            f.write(i)
    f.close()
    return


def save_ave_std_to_file(ave, std):
    "Save the average and tandard deviation to ave_std.txt"
    with open(args.dir + "/ave_std.txt", "w") as f:
        f.writelines("Average: " + ave + ", " + "Standard deviation: " + std)
    f.close()
    return

def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    os.system("sysctl -w net.ipv4.tcp_congestion_control=%s" % args.cong)

    # Cleanup any leftovers from previous mininet runs
    cleanup()

    topo = BBTopo()
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    # This dumps the topology and how nodes are interconnected through
    # links.
    dumpNodeConnections(net.hosts)
    # This performs a basic all pairs ping test.
    net.pingAll()

    # Start all the monitoring processes
    start_tcpprobe("cwnd.txt")
    start_ping(net)

    # TODO: Start monitoring the queue sizes.  Since the switch I
    # created is "s0", I monitor one of the interfaces.  Which
    # interface?  The interface numbering starts with 1 and increases.
    # Depending on the order you add links to your network, this
    # number may be 1 or 2.  Ensure you use the correct number.
    #
    qmon = start_qmon(iface='s0-eth2', outfile='%s/q.txt' % (args.dir))
    # qmon = None

    # TODO: Start iperf, webservers, etc.
    start_iperf(net)
    start_webserver(net)

    # Hint: The command below invokes a CLI which you can use to
    # debug.  It allows you to run arbitrary commands inside your
    # emulated hosts h1 and h2.
    #
    # CLI(net)

    # TODO: measure the time it takes to complete webpage transfer
    # from h1 to h2 (say) 3 times.  Hint: check what the following
    # command does: curl -o /dev/null -s -w %{time_total} google.com
    # Now use the curl command to fetch webpage from the webserver you
    # spawned on host h1 (not from google!)
    # Hint: have a separate function to do this and you may find the
    # loop below useful.
    h1 = net.get('h1')
    h2 = net.get('h2')
    #Record the start time to help us know whether we should stop the simulation
    start_time = time()

    #The list save the download times in fixed duration
    fetch_times = []

    #The list save tuples (fetch time point, download time) (which is [fetch_clock, float(fetch_time)] returned by measure_fetch_time)
    measure_data = []
    while True:
        # do the measurement (say) 3 times.
        fetch_info = measure_fetch_time(h1, h2)

        #get the download time
        fetch_time = fetch_info[1]
        print "fetch time %s" % fetch_time

        #add every download time to the list
        fetch_times.append(float(fetch_time))

        #add every tuple (fetch time point, download time) to the list
        measure_data.append(fetch_info)

        #download the webpage from h1 every two seconds
        sleep(1)
        now = time()
        delta = now - start_time
        if delta > args.time:
            break
        print "%.1fs left..." % (args.time - delta)

    #save the time points and download times to the file
    save_download_time_to_file(measure_data)

    # TODO: compute average (and standard deviation) of the fetch
    # times.  You don't need to plot them.  Just note it in your
    # README and explain.
    ave = helper.avg(fetch_times)
    std = helper.stdev(fetch_times)
    print "Average: " + str(ave)
    print "Standard deviation: " + str(std)

    #save the average (and standard deviation) of the fetch to the file
    save_ave_std_to_file(str(ave), str(std))

    stop_tcpprobe()
    if qmon is not None:
        qmon.terminate()
    net.stop()
    # Ensure that all processes you create within Mininet are killed.
    # Sometimes they require manual killing.
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()


if __name__ == "__main__":
    bufferbloat()
