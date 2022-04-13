
import uhd
import math
from threading import Thread, Lock
import numpy as np
import inspect


class AhcUhdUtils:
    INIT_DELAY = 0.05  # 50mS initial delay before transmit
    samps_per_est = 100
    #bandwidth = 250000
    #freq =2462000000.0
    lo_offset = 0
    
    wave_freq=10000
    wave_ampl = 0.3
    #hw_tx_gain = 70.0           # hardware tx antenna gain
    #hw_rx_gain = 20.0           # hardware rx antenna gain
    duration = 1
    
    
    def __init__(self, componentinstancenumber):
        self.mutex = Lock()
        self.cca = False
        self.componentinstancenumber = componentinstancenumber
        
    def on_init(self):
        pass
    
    def configureUsrp(self, devicename, type="b200", freq =2162000000.0, bandwidth = 1000000, chan = 0, hw_tx_gain = 50.0, hw_rx_gain = 20.0):
            
        self.devicename = devicename
        self.freq = freq
        self.bandwidth = bandwidth
        self.chan = chan
        self.hw_tx_gain = hw_tx_gain
        self.hw_rx_gain = hw_rx_gain
        self.tx_rate= self.bandwidth
        self.rx_rate= self.bandwidth
        print(f"Configuring type={type},devicename={devicename}, freq={freq}, bandwidth={bandwidth}, channel={chan}, hw_tx_gain={hw_tx_gain}, hw_rx_gain={hw_rx_gain}")
        self.usrp = uhd.usrp.MultiUSRP(f"name={devicename}")
        
        self.usrp.set_rx_bandwidth(self.bandwidth, self.chan)
        self.usrp.set_tx_bandwidth(self.bandwidth, self.chan)
        
        self.usrp.set_rx_freq(self.freq, self.chan)
        self.usrp.set_tx_freq(self.freq, self.chan)
        
        self.usrp.set_rx_bandwidth(self.bandwidth,self.chan)
        self.usrp.set_tx_bandwidth(self.bandwidth,self.chan)
        
        self.usrp.set_rx_rate(self.tx_rate, self.chan)
        self.usrp.set_tx_rate(self.rx_rate, self.chan)
        
        self.usrp.set_rx_gain(self.hw_rx_gain, self.chan)
        self.usrp.set_tx_gain(self.hw_tx_gain, self.chan)

        #self.usrp.set_rx_agc(True, self.chan)
        

        stream_args = uhd.usrp.StreamArgs('fc32', 'sc16')
        stream_args.channels = [self.chan]
        
        self.rx_streamer = self.usrp.get_rx_stream(stream_args)
        self.tx_streamer = self.usrp.get_tx_stream(stream_args)
    
    def get_usrp_power(self,num_samps=1000000, chan=0):
        uhd.dsp.signals.get_usrp_power(self.rx_streamer, num_samps, chan)
        
    
    def ischannelclear(self, threshold=-70, pout=100):
        self.cca = True
        cca_threshold = threshold + 10*math.log10(100/pout)
        tx_rate = self.usrp.get_rx_rate(self.chan) / 1e6
        samps_per_est = math.floor(18 * tx_rate)
        #samps_per_est = 10
        power_dbfs = 0
        self.mutex.acquire(1)
        try:
            power_dbfs = uhd.dsp.signals.get_usrp_power(self.rx_streamer, num_samps=int(samps_per_est), chan=self.chan)
        except Exception as e:
            print("Exception in CCA: ", e)
        finally:
            self.mutex.release()
            self.start_usrp_rx()
        #print("Power-dbfs=", power_dbfs)
        self.cca = False
        if (power_dbfs > cca_threshold ):
            #print(power_dbfs)
            return False, power_dbfs
        else:
            return True, power_dbfs
    
    def start_rx(self, rx_callback, framer):
        print(f"start_rx on usrp winslab_b210_{self.componentinstancenumber}")
        self.framer = framer
        self.rx_callback = rx_callback
        self.rx_rate = self.usrp.get_rx_rate()
        self.start_usrp_rx()
        t = Thread(target=self.rx_thread, args=[])
        t.daemon = True
        t.start()
        

    def start_usrp_rx(self):
        #print(f"start_usrp_rx on usrp winslab_b210_{self.componentinstancenumber}")
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        self.rx_streamer.issue_stream_cmd(stream_cmd)
        
    def stop_usrp_rx(self):
        self.rx_streamer.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))
        
    def rx_thread(self):
        print(f"rx_thread on usrp winslab_b210_{self.componentinstancenumber}")
        #print(f"max_samps_per_packet={max_samps_per_packet}")
        
        #print(f"recv_buffer={recv_buffer")
        while(True):
            if self.cca == False:
                self.mutex.acquire(1)
                #print(f"rx_thread on usrp winslab_b210_{self.componentinstancenumber} ---> {self.devicename}")
                try:
                    had_an_overflow = False
                    rx_metadata = uhd.types.RXMetadata()
                    max_samps_per_packet = self.rx_streamer.get_max_num_samps()
                    recv_buffer = np.zeros( max_samps_per_packet, dtype=np.complex64)
                    
                    num_rx_samps = self.rx_streamer.recv(recv_buffer, rx_metadata)
                    
                    #print(f"num_rx_samps={num_rx_samps}")
                    self.rx_callback(num_rx_samps, recv_buffer)
                    #print(f"rx_thread on usrp winslab_b210_{self.componentinstancenumber} ---> {self.devicename}\t{self.rx_callback}")
                except RuntimeError as ex:
                    print("Runtime error in receive: %s", ex)
                finally:
                    self.mutex.release()
                if rx_metadata.error_code == uhd.types.RXMetadataErrorCode.none:
                    pass
                elif rx_metadata.error_code == uhd.types.RXMetadataErrorCode.overflow:
                    #print("Receiver error: overflow  %s, continuing...", rx_metadata.strerror())
                    pass
                elif rx_metadata.error_code == uhd.types.RXMetadataErrorCode.late:
                    #print("Receiver error: late %s, continuing...", rx_metadata.strerror())
                    pass
                elif rx_metadata.error_code == uhd.types.RXMetadataErrorCode.timeout:
                    print("Receiver error:timeout  %s, continuing...", rx_metadata.strerror())
                    pass
                else:
                    print("Receiver error: %s", rx_metadata.strerror())
                    
        
    def finalize_transmit_samples(self):   
        tx_metadata = uhd.types.TXMetadata() 
        tx_metadata.end_of_burst = True
        tx_metadata.start_of_burst = False
        tx_metadata.has_time_spec = False
        num_tx_samps = self.tx_streamer.send(np.zeros((1, 0), dtype=np.complex64), tx_metadata)
        #self.tx_streamer.send(np.zeros(1, dtype=np.complex64), tx_metadata)
        #self.start_usrp_rx()
        
    def transmit_samples(self, transmit_buffer):
        #self.stop_usrp_rx()
        tx_metadata = uhd.types.TXMetadata()
        tx_metadata.has_time_spec = False
        tx_metadata.start_of_burst = False
        tx_metadata.end_of_burst = False
        #print(transmit_buffer)
        num_tx_samps = self.tx_streamer.send(transmit_buffer, tx_metadata)
        #print("num_tx_samples", num_tx_samps)
        # Send a mini EOB packet
        #tx_metadata.end_of_burst = True
        #self.tx_streamer.send(np.zeros((1,0), dtype=np.complex), tx_metadata)