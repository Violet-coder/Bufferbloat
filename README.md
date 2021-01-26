# Bufferbloat
Emulate the network to study what happens when we down load data from a remote reserver to the End Host in Mininet.

The figure shows a “typical” home network with a Home Router connected to an end host. The Home Router is connected via Cable or DSL to a Headend router at the Internet access provider’s office.

![image](https://github.com/Violet-coder/Bufferbloat/blob/master/bufferbloatLogic.png)

In the simulation we could see:

- dynamics of TCP sawtooth and router buffer occupancy in a network.
- why large router buffers can lead to poor performance. This problem is often called “*bufferbloat*.”
-  how to use Mininet to run traffic generators, collect statistics and plot them.

