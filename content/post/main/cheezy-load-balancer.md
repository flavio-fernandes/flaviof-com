+++
author = "flaviof"
categories = [ "main", "hacks" ]
date = "2018-07-19T16:20:22-04:00"
tags = [ "go" ]
title = "Goroutines to load balance"
series = "go"
+++

A basic example of using worker pool to load balance TCP connections.

<!--more-->

I was curious to see how easy it would be to implement goroutines.
To that end, I decided to write a load balancer for TCP, where a Golang process would
listen and accept connections, and then simply proxy it to a backend application.

### Load Balancer Diagram

```
       +-------------------------------+
       |                               |     +----------------+ 
       |               ----SocketWorker1.1----->   Flask App  | 
       |  Goland App   <---SocketWorker1.2-------  Backend 1  | 
       |                               |     +----------------+ 
       |                               |
       |                               |     +----------------+ 
       |  Frontend     ----SocketWorker2.1----->   Flask App  | 
----------->           <---SocketWorker2.2-------  Backend 2  | 
       |  Listen                       |     +----------------+ 
       |  Socket            ...        |
       |                               |     +----------------+ 
       |               ----SocketWorkerX.1----->   Flask App  | 
       |               <---SocketWorkerX.2-------  Backend X  | 
       |                               |     +----------------+ 
       +-------------------------------+
```

### Backend App

Since the focus was on Golang, I wrote a super simple Flask app to handle 
HTTP requests. The bulk of that involved writing this:

```
from app import app
import os

@app.route('/')
def index():
    return os.environ.get("MSG", "Hello, World!")
```

### Connection Handling

Upon accepting a connection on TCP socket, a handler function in go is
spawned to perform the following steps on a new client socket:

  * Pick a backend Flask Server and open a socket connection to it;
  * Spawn a worker to copy data from client to backend;
  * Spawn a worker to copy data from backend to client;
  * Wait until both workers finish;
  * Close client and backend sockets.

The socket worker itself does a very basic job. Given 2 sockets, 
loop on reading from the first socket and writing to the second socket.

```
func(connFrom net.Conn, connTo net.Conn) {
    var err error = nil
    var readLen int
    var readDone = false
    var writeOffset int
    var writeLen int

    // Make a buffer to hold incoming data
    buf := make([]byte, 1024)

    for !readDone && err == nil {
        // Read from connFrom, up to buf size
        readLen, err = connFrom.Read(buf)
        if err != nil {
            if err != io.EOF {
                break
            }
            readDone = true
        }

        // Write to connTo
        writeOffset = 0
        for writeOffset < readLen {
            writeLen, err = connTo.Write(buf[writeOffset:readLen])
            if err != nil {
                break
            }
            writeOffset += writeLen
        }
    }
}
```

The complete code is located [here](https://github.com/flavio-fernandes/basic-lb/blob/master/lb.go)

### Trying it out

You can use Vagrant and the following steps to try this out in a virtual machine.
First, install an HV (like [VirtualBox](https://www.virtualbox.org)) and
[Vagrant](https://www.vagrantup.com/downloads.html). Then use these commands:

```
git clone https://github.com/flavio-fernandes/basic-lb.git
cd basic-lb

# start vm
vagrant up 

# ssh into vm
vagrant ssh

# launch 3 backend httpds
cd ~/httpd && export FLASK_APP=httpd.py
for PORT in {8101..8103}; do \
    export MSG="hello from server on port ${PORT}"
    screen -S "httpd_port_${PORT}" -d -m \
        flask run --port $PORT
done

# Build Golang application, if needed
cd ~/lbapp && [ -e ./lb ] || go build lb.go

# launch frontend lb, port 8080
screen -S "lb_port_8080" -d -m \
        ~/lbapp/lb -f 8080 -p 8101 -p 8102 -p 8103

# See the screen sessions just launched
screen -ls
ps auxww | grep -e flask -e lb

# You can attach to screen any screen by doing
#
# screen -r httpd_port_${PORT}
# screen -r lb_port_8080
#
# <contral> + "a" + "d" to detach

# Hit load balancer with some HTTP requests
for i in {1..10}; do \
   curl http://127.0.0.1:8080
   echo
done

# Background multiple requests
for i in {1..10}; do curl http://127.0.0.1:8080 & echo ok; echo; done

# Cleanup
killall flask ; killall lb
rm -f ~/lbapp/lb

# Exit session in vm and destroy it
exit
vagrant destroy -f
```

### Conclusion

It is extremely easy to leverage workers in Golang to delegate the handling of TCP
connections. As expected. ;)

### Reference links

* [Go by example](https://gobyexample.com/)
* [Go by example: Goroutines](https://gobyexample.com/goroutines)

