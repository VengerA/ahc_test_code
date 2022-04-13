from cgi import print_exception
import time, random, math
from enum import Enum
from adhoccomputing import GenericModel, Event, Generics, Definitions, Topology, FramerObjects, FrameHandlerBase, ofdm_callback, MacCsmaPPersistentConfigurationParameters, MacCsmaPPersistent
from LiquidDsputils import *
from Uhdutils import *
from ctypes import *
import queue
import pickle


# define your own message types
class ApplicationLayerMessageTypes(Enum):
    BROADCAST = "BROADCAST"


# define your own message header structure
class ApplicationLayerMessageHeader(Generics.GenericMessageHeader):
    pass


class UsrpApplicationLayerEventTypes(Enum):
    STARTBROADCAST = "startbroadcast"


class UsrpApplicationLayer(GenericModel):
    # def on_init(self, eventobj: Event):

    def __init__(self, componentname, componentid):
        super().__init__(componentname, componentid)
        self.counter = 0
        self.eventhandlers[UsrpApplicationLayerEventTypes.STARTBROADCAST] = self.on_startbroadcast

    def on_message_from_top(self, eventobj: Event):
    # print(f"I am {self.componentname}.{self.componentinstancenumber},sending down eventcontent={eventobj.eventcontent}\n")
        self.send_down(Event(self, Definitions.EventTypes.MFRT, eventobj.eventcontent))

    def on_message_from_bottom(self, eventobj: Event):
        evt = Event(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
        print(f"I am Node.{self.componentinstancenumber}, received from Node.{eventobj.eventcontent.header.messagefrom} a message: {eventobj.eventcontent.payload}")
        if self.componentinstancenumber == 1:
            evt.eventcontent.header.messageto = 0
            evt.eventcontent.header.messagefrom = 1
        else:
            evt.eventcontent.header.messageto = 1
            evt.eventcontent.header.messagefrom = 0
        evt.eventcontent.payload = eventobj.eventcontent.payload
        #print(f"I am {self.componentname}.{self.componentinstancenumber}, sending down eventcontent={eventobj.eventcontent.payload}\n")
        self.send_down(evt)  # PINGPONG

    def on_startbroadcast(self, eventobj: Event):
        if self.componentinstancenumber == 1:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 1, 0)
        else:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 0, 1)
        self.counter = self.counter + 1

        payload = "BMSG-" + str(self.counter)
        broadcastmessage = Generics.GenericMessage(hdr, payload)
        evt = Event(self, Definitions.EventTypes.MFRT, broadcastmessage)
        # time.sleep(3)
        self.send_down(evt)



# define your own message header structure
class UsrpB210PhyMessageHeader(Generics.GenericMessageHeader):
    pass


# define your own message payload structure
class UsrpB210PhyMessagePayload(Generics.GenericMessagePayload):

  def __init__(self, header, payload):
    self.phyheader = header
    self.phypayload = payload

class UsrpB210OfdmFlexFramePhy(FrameHandlerBase):

    def on_init(self, eventobj: Event):
        #print("initialize LiquidDspOfdmFlexFrameHandler")
        pass

    def send_self(self, event: Event):
        self.trigger_event(event)

    def rx_callback(self, num_rx_samps, recv_buffer):
        try:
            #print("Self.fs", self.fs)
            ofdmflexframesync_execute(self.fs, recv_buffer.ctypes.data_as(POINTER(struct_c__SA_liquid_float_complex)) , num_rx_samps)
        except Exception as ex:
            print("Exception1", ex)


    def transmit(self, _header, _payload, _payload_len, _mod, _fec0, _fec1):
        #self.fgprops.mod_scheme = _mod
        #self.fgprops.fec0 = _fec0
        #self.fgprops.fec1 = _fec1
        #ofdmflexframegen_setprops(self.fg, byref(self.fgprops))
        ofdmflexframegen_assemble(self.fg, _header, _payload, _payload_len)
        # print("assembled")
        last_symbol = False
        while (last_symbol == 0):
            fgbuffer = np.zeros(self.fgbuffer_len, dtype=np.complex64)

            last_symbol = ofdmflexframegen_write(self.fg, fgbuffer.ctypes.data_as(POINTER(struct_c__SA_liquid_float_complex)), self.fgbuffer_len)
            #for i in range(self.fgbuffer_len):
            #    fgbuffer[i] = fgbuffer[i] * 2
            try:
                self.ahcuhd.transmit_samples(fgbuffer)
                # self.rx_callback(self.fgbuffer_len, npfgbuffer) #loopback for trial
            except Exception as e:
                print("Exception in transmit", e)
        self.ahcuhd.finalize_transmit_samples()
        #ofdmflexframesync_print(self.fs)


    def configure(self):
        self.fgprops = ofdmflexframegenprops_s(LIQUID_CRC_32, LIQUID_FEC_NONE, LIQUID_FEC_HAMMING74, LIQUID_MODEM_QPSK)
        res = ofdmflexframegenprops_init_default(byref(self.fgprops))
        self.fgprops.check = LIQUID_CRC_32
        self.fgprops.fec0 = LIQUID_FEC_NONE
        self.fgprops.fec1 = LIQUID_FEC_HAMMING74
        self.fgprops.mod_scheme = LIQUID_MODEM_QPSK
        self.fgprops.M = 512
        self.fgprops.cp_len = 64
        self.fgprops.taper_len = 64
        self.fgbuffer_len = self.fgprops.M + self.fgprops.cp_len

        self.fg = ofdmflexframegen_create(self.fgprops.M, self.fgprops.cp_len, self.fgprops.taper_len, None, byref(self.fgprops))

        res = ofdmflexframegen_print(self.fg)

        self.ofdm_callback_function = framesync_callback(ofdm_callback)

        try:
            # WILL PASS ID of THIS OBJECT in userdata then will find the object in FramerObjects
            self.fs = ofdmflexframesync_create(self.fgprops.M, self.fgprops.cp_len, self.fgprops.taper_len, None, self.ofdm_callback_function, id(self))
            print("fs", self.fs, id(self))
        except Exception as ex:
            print("Exception2", ex)

        self.ahcuhd.start_rx(self.rx_callback, self)
        ofdmflexframegen_reset(self.fg)
        ofdmflexframesync_reset(self.fs)


# Callbacks have to be outside since the c library does not like "self"
# Because of this reason will use userdata to get access back to the framer object

    def __init__(self, componentname, componentinstancenumber):
        super().__init__(componentname, componentinstancenumber)


class UsrpNode(GenericModel):
    counter = 0
    def on_init(self, eventobj: Event):
        pass

    def __init__(self, componentname, componentid):
        # SUBCOMPONENTS

        macconfig = MacCsmaPPersistentConfigurationParameters(0.5)

        self.appl = UsrpApplicationLayer("UsrpApplicationLayer", componentid)
        self.phy = UsrpB210OfdmFlexFramePhy("UsrpB210OfdmFlexFramePhy", componentid)
        self.mac = MacCsmaPPersistent("MacCsmaPPersistent", componentid,  configurationparameters=macconfig, uhd=self.phy.ahcuhd)

        # CONNECTIONS AMONG SUBCOMPONENTS
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.UP, self) #Not required if nodemodel will do nothing
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.mac)

        self.mac.connect_me_to_component(Definitions.ConnectorTypes.UP, self.appl)
        self.mac.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.phy)

        # Connect the bottom component to the composite component....
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.UP, self.mac)
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self)

        # self.phy.connect_me_to_component(ConnectorTypes.DOWN, self)
        # self.connect_me_to_component(ConnectorTypes.DOWN, self.appl)

        super().__init__(componentname, componentid)

def main():
    topo = Topology()
# Note that the Topology has to specific: usrp winslab_b210_0 is run by instance 0 of the component
# Therefore, the usrps have to have names winslab_b210_x where x \in (0 to nodecount-1)
    topo.construct_winslab_topology_without_channels(4, UsrpNode)
  # topo.construct_winslab_Topology_with_channels(2, UsrpNode, FIFOBroadcastPerfectChannel)

  # time.sleep(1)
  # topo.nodes[0].send_self(Event(topo.nodes[0], UsrpNodeEventTypes.STARTBROADCAST, None))

    topo.start()
    i = 0
    while(i < 10):
        topo.nodes[1].appl.send_self(Event(topo.nodes[0], UsrpApplicationLayerEventTypes.STARTBROADCAST, None))
        time.sleep(1)
        i = i + 1


if __name__ == "__main__":
    main()


