# Benchmark of shared memory plugins

# Prerequisites
redis-server should be installed and running.
you can run redis-server with the following command:
```bash
mkdir /tmp/redis && sudo chmod 777 /tmp/redis
docker run -d -p 6379:6379 -v /tmp/redis:/tmp/redis --name redis redis redis-server --unixsocket /tmp/redis/redis.sock --port 6379
sudo chmod 777 /tmp/redis/redis.sock
```

# Run

`python ./shm.py`

# Results

For a batch of data, K is the batch size:
`pipe` is to get K ids in pipe, then set K values in pipe.
`pipe2` is to *set value then get netx_id* in pipe for K times.

The benchmark on my machine(AMD Ryzen 9 5900X) is as follows:

|method*duplicate        | size           | min                    | mid            | max            | 95%            | std           |
|------------------------|----------------|------------------------|----------------|----------------|----------------|---------------|
|plasma_store    *1      |size:         1 |times: min(0.00021825)  |mid(0.00029007) |max(0.12717)    |95%(0.0002363)  |Std.(0.0023571)|
|redis_unix      *1      |size:         1 |times: min(0.00017678)  |mid(0.00024492) |max(0.00065411) |95%(0.00020866) |Std.(4.9412e-05)|
|redis_unix_pipe*1       |size:         1 |times: min(0.00020062)  |mid(0.00026453) |max(0.00062387) |95%(0.00021436) |Std.(4.925e-05)|
|redis_unix_pipe2*1      |size:         1 |times: min(0.00015132)  |mid(0.0001966)  |max(0.00043711) |95%(0.00015908) |Std.(3.1591e-05)|
|redis_tcp       *1      |size:         1 |times: min(0.00099975)  |mid(0.0010672)  |max(0.0018774)  |95%(0.0010118)  |Std.(7.8258e-05)|
|redis_tcp_pipe*1        |size:         1 |times: min(0.00082964)  |mid(0.00091998) |max(0.0013861)  |95%(0.00084248) |Std.(0.00010554)|
|redis_tcp_pipe2*1       |size:         1 |times: min(0.00056842)  |mid(0.00061605) |max(0.0010323)  |95%(0.00057813) |Std.(4.2798e-05)|
|plasma_store    *10     |size:         1 |times: min(0.0014458)   |mid(0.0015366)  |max(0.0022819)  |95%(0.0014635)  |Std.(0.00010028)|
|redis_unix      *10     |size:         1 |times: min(0.0013734)   |mid(0.0018505)  |max(0.002883)   |95%(0.0014747)  |Std.(0.00021839)|
|redis_unix_pipe*10      |size:         1 |times: min(0.00041485)  |mid(0.00046185) |max(0.00087291) |95%(0.00043372) |Std.(5.1879e-05)|
|redis_unix_pipe2*10     |size:         1 |times: min(0.00097136)  |mid(0.0010425)  |max(0.0017049)  |95%(0.00098117) |Std.(9.282e-05)|
|redis_tcp       *10     |size:         1 |times: min(0.0077813)   |mid(0.0082085)  |max(0.011144)   |95%(0.0078249)  |Std.(0.00033215)|
|redis_tcp_pipe*10       |size:         1 |times: min(0.00099664)  |mid(0.0010935)  |max(0.010853)   |95%(0.0010157)  |Std.(0.00033583)|
|redis_tcp_pipe2*10      |size:         1 |times: min(0.0031447)   |mid(0.0033145)  |max(0.0040558)  |95%(0.0031991)  |Std.(0.00012204)|
|plasma_store    *1      |size:      1024 |times: min(0.00021201)  |mid(0.00024914) |max(0.00072214) |95%(0.000231)   |Std.(3.1313e-05)|
|redis_unix      *1      |size:      1024 |times: min(0.00018911)  |mid(0.00026299) |max(0.00062975) |95%(0.0002045)  |Std.(5.4899e-05)|
|redis_unix_pipe*1       |size:      1024 |times: min(0.00025713)  |mid(0.00033807) |max(0.0006484)  |95%(0.00026262) |Std.(5.1035e-05)|
|redis_unix_pipe2*1      |size:      1024 |times: min(0.00018833)  |mid(0.00023925) |max(0.00048655) |95%(0.00019409) |Std.(4.7112e-05)|
|redis_tcp       *1      |size:      1024 |times: min(0.0010173)   |mid(0.0011594)  |max(0.0015927)  |95%(0.0010379)  |Std.(9.1125e-05)|
|redis_tcp_pipe*1        |size:      1024 |times: min(0.00086598)  |mid(0.00098137) |max(0.001697)   |95%(0.00088563) |Std.(9.1244e-05)|
|redis_tcp_pipe2*1       |size:      1024 |times: min(0.00059048)  |mid(0.00068122) |max(0.0012206)  |95%(0.00060695) |Std.(7.28e-05)|
|plasma_store    *10     |size:      1024 |times: min(0.0014056)   |mid(0.0016776)  |max(0.0025911)  |95%(0.0014181)  |Std.(0.00017302)|
|redis_unix      *10     |size:      1024 |times: min(0.001523)    |mid(0.0019006)  |max(0.0032806)  |95%(0.0016197)  |Std.(0.00024036)|
|redis_unix_pipe*10      |size:      1024 |times: min(0.00043038)  |mid(0.00047443) |max(0.00085595) |95%(0.00043567) |Std.(5.8508e-05)|
|redis_unix_pipe2*10     |size:      1024 |times: min(0.0010308)   |mid(0.0011158)  |max(0.0017399)  |95%(0.0010569)  |Std.(8.8131e-05)|
|redis_tcp       *10     |size:      1024 |times: min(0.0080652)   |mid(0.0085976)  |max(0.0099671)  |95%(0.0081722)  |Std.(0.0002765)|
|redis_tcp_pipe*10       |size:      1024 |times: min(0.0012667)   |mid(0.0015343)  |max(0.011259)   |95%(0.0013054)  |Std.(0.00041793)|
|redis_tcp_pipe2*10      |size:      1024 |times: min(0.0034979)   |mid(0.004031)   |max(0.17999)    |95%(0.0035847)  |Std.(0.0136)|
|plasma_store    *1      |size:     65536 |times: min(0.0005568)   |mid(0.00063401) |max(0.0014486)  |95%(0.00056195) |Std.(8.1771e-05)|
|redis_unix      *1      |size:     65536 |times: min(0.001083)    |mid(0.0012308)  |max(0.0018406)  |95%(0.0011115)  |Std.(0.00010089)|
|redis_unix_pipe*1       |size:     65536 |times: min(0.0010901)   |mid(0.0012305)  |max(0.0017836)  |95%(0.001119)   |Std.(0.00010447)|
|redis_unix_pipe2*1      |size:     65536 |times: min(0.0010396)   |mid(0.0012008)  |max(0.0018188)  |95%(0.0010666)  |Std.(0.00011022)|
|redis_tcp       *1      |size:     65536 |times: min(0.0045755)   |mid(0.0051557)  |max(0.0063323)  |95%(0.0046079)  |Std.(0.00029353)|
|redis_tcp_pipe*1        |size:     65536 |times: min(0.0043814)   |mid(0.0051017)  |max(0.25678)    |95%(0.0044502)  |Std.(0.017752)|
|redis_tcp_pipe2*1       |size:     65536 |times: min(0.0034682)   |mid(0.0039918)  |max(0.082128)   |95%(0.0035257)  |Std.(0.004511)|
|plasma_store    *10     |size:     65536 |times: min(0.0042992)   |mid(0.0049836)  |max(0.0075222)  |95%(0.0043859)  |Std.(0.00036683)|
|redis_unix      *10     |size:     65536 |times: min(0.0049159)   |mid(0.0059624)  |max(0.0094144)  |95%(0.0049767)  |Std.(0.0010004)|
|redis_unix_pipe*10      |size:     65536 |times: min(0.0040042)   |mid(0.0049775)  |max(0.0067737)  |95%(0.0041353)  |Std.(0.00038772)|
|redis_unix_pipe2*10     |size:     65536 |times: min(0.0046175)   |mid(0.0052759)  |max(0.0072151)  |95%(0.0047667)  |Std.(0.00045483)|
|redis_tcp       *10     |size:     65536 |times: min(0.038987)    |mid(0.040888)   |max(0.36523)    |95%(0.039126)   |Std.(0.037688)|
|redis_tcp_pipe*10       |size:     65536 |times: min(0.031887)    |mid(0.033399)   |max(0.038865)   |95%(0.031939)   |Std.(0.0016838)|
|redis_tcp_pipe2*10      |size:     65536 |times: min(0.03391)     |mid(0.035419)   |max(0.042874)   |95%(0.034054)   |Std.(0.0020511)|
|plasma_store    *1      |size:   3145728 |times: min(0.013337)    |mid(0.014126)   |max(0.54812)    |95%(0.013362)   |Std.(0.083294)|
|redis_unix      *1      |size:   3145728 |times: min(0.051948)    |mid(0.053129)   |max(0.059592)   |95%(0.051954)   |Std.(0.0019071)|
|redis_unix_pipe*1       |size:   3145728 |times: min(0.050514)    |mid(0.052103)   |max(0.055304)   |95%(0.050515)   |Std.(0.0014177)|
|redis_unix_pipe2*1      |size:   3145728 |times: min(0.050124)    |mid(0.054984)   |max(0.071521)   |95%(0.05032)    |Std.(0.0040623)|
|redis_tcp       *1      |size:   3145728 |times: min(0.17762)     |mid(0.18884)    |max(0.20003)    |95%(0.17836)    |Std.(0.0056087)|
|redis_tcp_pipe*1        |size:   3145728 |times: min(0.18306)     |mid(0.18502)    |max(0.33999)    |95%(0.18308)    |Std.(0.048725)|
|redis_tcp_pipe2*1       |size:   3145728 |times: min(0.1785)      |mid(0.18269)    |max(0.20972)    |95%(0.17876)    |Std.(0.009486)|
|plasma_store    *10     |size:   3145728 |times: min(0.11297)     |mid(0.12553)    |max(0.15475)    |95%(0.11328)    |Std.(0.011844)|
|redis_unix      *10     |size:   3145728 |times: min(0.37283)     |mid(0.38705)    |max(0.40958)    |95%(0.37301)    |Std.(0.010967)|
|redis_unix_pipe*10      |size:   3145728 |times: min(0.3782)      |mid(0.42633)    |max(0.51581)    |95%(0.38039)    |Std.(0.035545)|
|redis_unix_pipe2*10     |size:   3145728 |times: min(0.39654)     |mid(0.45153)    |max(0.50846)    |95%(0.39915)    |Std.(0.028468)|
|redis_tcp       *10     |size:   3145728 |times: min(1.8532)      |mid(1.8908)     |max(1.9947)     |95%(1.854)      |Std.(0.040474)|
|redis_tcp_pipe*10       |size:   3145728 |times: min(1.7741)      |mid(1.8233)     |max(1.8485)     |95%(1.7745)     |Std.(0.024004)|
|redis_tcp_pipe2*10      |size:   3145728 |times: min(1.8035)      |mid(1.8497)     |max(1.9332)     |95%(1.8036)     |Std.(0.043216)|

We can see the performance rank: redis unix > plasma > redis tcp in general.
And when batch size is large, pipe can be better than pipe2 while when batch size is small, pipe2 is better than pipe.
