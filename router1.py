import socket
import sys
import time
import os
import glob


# helper functions

# set up a socket connection
def create_socket(host, port):
    # create a socket
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # connect the socket to the host and port
    try:
        soc.connect((host, port))
    except:
        print("Connection Error to", port)
        sys.exit()
    return soc


# read in a csv file
def read_csv(path):
    # open the file to read
    table_file = open(path, "r")
    # store each line
    table = table_file.readlines()
    # create an empty list to store each processed row
    table_list = []
    for line in table:
        # split it by the delimiter
        row = line.strip().split(",")
        # remove any leading or trailing spaces in each element
        row = [x.strip() for x in row]
        # append the resulting list
        table_list.append(row)
    # close the file
    table_file.close()
    return table_list


# find the default port when no match is found in the forwarding table for a packets destination IP
def find_default_gateway(table):
    # traverse the table
    for row in table:
        if row[0] == "0.0.0.0":
            # return the interface of that row
            return row[3]
    return None


# generate a forwarding table that has the IP range for a given interface
def generate_forwarding_table_with_range(table):
    # to store the new forwarding table
    new_table = []
    # traverse old forwarding table
    for row in table:
        # process each network destination other than 0.0.0.0
        if row[0] != "0.0.0.0":
            # store the network destination and netmask
            network_dst_string = row[0]
            netmask_string = row[1]
            # find ip range
            ip_range = find_ip_range(network_dst_string, netmask_string)
            new_row = [ip_range[0], ip_range[1], row[3], row[2]]
            # append the new row we created
            new_table.append(new_row)
    return new_table


# convert a string IP to its binary representation
def ip_to_bin(ip):
    # split ip into octets
    ip_octets = ip.split(".")
    # create an empty string to store each binary octet
    ip_bin_string = ""
    # traverse the ip
    for octet in ip_octets:
        int_octet = int(octet)
        # convert decimal int to binary
        bin_octet = bin(int_octet)
        # convert the binary to string and remove the "0b" at beginning
        bin_octet_string = bin_octet[2:]
        # needs to be an octet because were working with ips
        while len(bin_octet_string) < 8:
            bin_octet_string = "0" + bin_octet_string
        # append the octet to ip_bin_string
        ip_bin_string = ip_bin_string + bin_octet_string
    # convert into an actual binary int
    ip_int = int(ip_bin_string, 2)
    return bin(ip_int)


# find the range of ips inside a given a destination ip address/subnet mask pair
def find_ip_range(network_dst, netmask):
    # perform a bitwise AND on the network destination and netmask to get the min ip in range
    bitwise_and = int(ip_to_bin(network_dst), 2) & int(ip_to_bin(netmask), 2)
    # perform a bitwise NOT on the netmask to get # of total ips in range
    compliment = bit_not(int(ip_to_bin(netmask), 2))
    min_ip = bitwise_and
    # add the total number of ips to the minimum ip to get max ip address in range
    max_ip = min_ip + compliment
    return [min_ip, max_ip]


# bitwise NOT on unsigned integer
def bit_not(n, numbits=32):
    return (1 << numbits) - 1 - n


# write packets or payload to file
def write_to_file(path, packet_to_write, send_to_router=None):
    # open output file for appending
    out_file = open(path, "a")
    # if not sending just append packet
    if send_to_router is None:
        out_file.write(packet_to_write + "\n")
    # else append packet plus recipient
    else:
        out_file.write(packet_to_write + " " + "to Router " + send_to_router + "\n")
    out_file.close()


# main program

# remove old output files before run
if not os.path.exists("output"):
    os.makedirs("output")
files = glob.glob('./output/*')
for f in files:
    os.remove(f)

# connect to sending ports
sock_8002 = create_socket("127.0.0.1", 8002)
sock_8004 = create_socket("127.0.0.1", 8004)

# read forwarding table and build table with ip ranges
forwarding_table = read_csv("input/router_1_table.csv")
default_gateway_port = find_default_gateway(forwarding_table)
forwarding_table_with_range = generate_forwarding_table_with_range(forwarding_table)

# read packets
packets_table = read_csv("input/packets.csv")

for packet_row in packets_table:
    sourceIP = packet_row[0]
    destinationIP = packet_row[1]
    payload = packet_row[2]
    ttl = int(packet_row[3])

    # decrement ttl and build new packet
    new_ttl = ttl - 1
    new_packet = sourceIP + "," + destinationIP + "," + payload + "," + str(new_ttl)

    # get dest ip as int for lookup
    destinationIP_bin = ip_to_bin(destinationIP)
    destinationIP_int = int(destinationIP_bin, 2)

    # find send interface from forwarding table
    send_interface = None
    is_last_hop = False
    for row in forwarding_table_with_range:
        if row[0] <= destinationIP_int <= row[1]:
            send_interface = row[2]
            is_last_hop = (send_interface == "127.0.0.1")
            break
    if send_interface is None:
        send_interface = default_gateway_port

    # if ttl>0 and not last hop send; if last hop write payload to out; else discard
    if not is_last_hop and new_ttl > 0 and send_interface == "8002":
        print("sending packet", new_packet, "to Router 2")
        write_to_file("output/sent_by_router_1.txt", new_packet, "2")
        sock_8002.send((new_packet + "\n").encode())
    elif not is_last_hop and new_ttl > 0 and send_interface == "8004":
        print("sending packet", new_packet, "to Router 4")
        write_to_file("output/sent_by_router_1.txt", new_packet, "4")
        sock_8004.send((new_packet + "\n").encode())
    elif is_last_hop:
        print("OUT:", payload)
        write_to_file("output/out_router_1.txt", payload)
    else:
        print("DISCARD:", new_packet)
        write_to_file("output/discarded_by_router_1.txt", new_packet)

    time.sleep(1)

# signal done to other routers
sock_8002.send("\n".encode())
sock_8004.send("\n".encode())
sock_8002.close()
sock_8004.close()
