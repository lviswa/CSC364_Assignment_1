import socket
import sys
import traceback
from threading import Thread


# helper functions

# set up a socket connection
def create_socket(host, port):
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        soc.connect((host, port))
    except:
        print("Connection Error to", port)
        sys.exit()
    return soc


# read in a csv file
def read_csv(path):
    table_file = open(path, "r")
    table = table_file.readlines()
    table_list = []
    for line in table:
        row = line.strip().split(",")
        row = [x.strip() for x in row]
        table_list.append(row)
    table_file.close()
    return table_list


# find default port when no match in forwarding table
def find_default_gateway(table):
    for row in table:
        if row[0] == "0.0.0.0":
            return row[3]
    return None


# generate forwarding table with ip range for each interface
def generate_forwarding_table_with_range(table):
    new_table = []
    for row in table:
        if row[0] != "0.0.0.0":
            network_dst_string = row[0]
            netmask_string = row[1]
            ip_range = find_ip_range(network_dst_string, netmask_string)
            new_row = [ip_range[0], ip_range[1], row[3], row[2]]
            new_table.append(new_row)
    return new_table


# convert string ip to binary representation
def ip_to_bin(ip):
    ip_octets = ip.split(".")
    ip_bin_string = ""
    for octet in ip_octets:
        int_octet = int(octet)
        bin_octet = bin(int_octet)
        bin_octet_string = bin_octet[2:]
        while len(bin_octet_string) < 8:
            bin_octet_string = "0" + bin_octet_string
        ip_bin_string = ip_bin_string + bin_octet_string
    ip_int = int(ip_bin_string, 2)
    return bin(ip_int)


# find range of ips for destination ip/subnet mask pair
def find_ip_range(network_dst, netmask):
    bitwise_and = int(ip_to_bin(network_dst), 2) & int(ip_to_bin(netmask), 2)
    compliment = bit_not(int(ip_to_bin(netmask), 2))
    min_ip = bitwise_and
    max_ip = min_ip + compliment
    return [min_ip, max_ip]


# bitwise NOT on unsigned integer
def bit_not(n, numbits=32):
    return (1 << numbits) - 1 - n


# receive and process incoming packet
def receive_packet(connection, max_buffer_size):
    received_packet = connection.recv(max_buffer_size)
    packet_size = sys.getsizeof(received_packet)
    if packet_size > max_buffer_size:
        print("The packet size is greater than expected", packet_size)
    decoded_packet = received_packet.decode().strip()
    print("received packet", decoded_packet)
    if decoded_packet:
        write_to_file("output/received_by_router_5.txt", decoded_packet)
    packet = decoded_packet.split(",") if decoded_packet else []
    return packet


# write packets or payload to file
def write_to_file(path, packet_to_write, send_to_router=None):
    out_file = open(path, "a")
    if send_to_router is None:
        out_file.write(packet_to_write + "\n")
    else:
        out_file.write(packet_to_write + " " + "to Router " + send_to_router + "\n")
    out_file.close()


# receive packets and forward or discard per 5(c), interface e=r4 sock_8006=r6
def processing_thread(connection, forwarding_table_with_range, default_gateway_port,
                     conn_from_r4, sock_8006, max_buffer_size=5120):
    while True:
        packet = receive_packet(connection, max_buffer_size)

        if not packet or len(packet) < 4:
            break

        sourceIP = packet[0]
        destinationIP = packet[1]
        payload = packet[2]
        ttl = int(packet[3])

        new_ttl = ttl - 1
        new_packet = sourceIP + "," + destinationIP + "," + payload + "," + str(new_ttl)

        destinationIP_bin = ip_to_bin(destinationIP)
        destinationIP_int = int(destinationIP_bin, 2)

        send_interface = None
        is_last_hop = False
        for row in forwarding_table_with_range:
            if row[0] <= destinationIP_int <= row[1]:
                send_interface = row[2]
                is_last_hop = (send_interface == "127.0.0.1")
                break

        if send_interface is None:
            send_interface = default_gateway_port
            is_last_hop = (default_gateway_port == "127.0.0.1")

        # send or out or discard
        if not is_last_hop and new_ttl > 0 and send_interface == "e":
            print("sending packet", new_packet, "to Router 4")
            write_to_file("output/sent_by_router_5.txt", new_packet, "4")
            conn_from_r4.send((new_packet + "\n").encode())
        elif not is_last_hop and new_ttl > 0 and send_interface == "8006":
            print("sending packet", new_packet, "to Router 6")
            write_to_file("output/sent_by_router_5.txt", new_packet, "6")
            sock_8006.send((new_packet + "\n").encode())
        elif is_last_hop:
            print("OUT:", payload)
            write_to_file("output/out_router_5.txt", payload)
        else:
            print("DISCARD:", new_packet)
            write_to_file("output/discarded_by_router_5.txt", new_packet)


# create server socket, listen, accept, spawn thread per connection
def start_server():
    host = "127.0.0.1"
    port = 8005
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    print("Socket created")
    try:
        soc.bind((host, port))
    except:
        print("Bind failed. Error : " + str(sys.exc_info()))
        sys.exit()
    soc.listen(5)
    print("Socket now listening")

    forwarding_table = read_csv("input/router_5_table.csv")
    default_gateway_port = find_default_gateway(forwarding_table)
    forwarding_table_with_range = generate_forwarding_table_with_range(forwarding_table)

    sock_8006 = create_socket(host, 8006)

    while True:
        connection, address = soc.accept()
        ip, port = address[0], str(address[1])
        print("Connected with " + ip + ":" + port)
        try:
            Thread(target=processing_thread, args=(connection, forwarding_table_with_range, default_gateway_port, connection, sock_8006)).start()
        except:
            print("Thread did not start.")
            traceback.print_exc()


# main program

if __name__ == "__main__":
    import os
    if not os.path.exists("output"):
        os.makedirs("output")
    start_server()
