import time, random, math
from enum import Enum
from adhoccomputing import GenericModel, GenericEvent, Generics, Definitions, Topology
from LiquidDsputils import *
from Uhdutils import *
from ctypes import *

import queue
import pickle
# from ahc import ComponentModel, Event, ConnectorTypes, Topology, EventTypes, GenericMessage, GenericMessageHeader, FramerObjects
# from ahc import ComponentRegistry
# from ahc.PhysicalLayers.UsrpB210OfdmFlexFramePhy import  UsrpB210OfdmFlexFramePhy
# from ahc.MAC.CSMA import MacCsmaPPersistent,MacCsmaPPersistentConfigurationParameter

class FramerObjects():
    framerobjects = {}
    ahcuhdubjects = {}
    def add_framer(self, id, obj):
        self.framerobjects[id] = obj

    def get_framer_by_id(self, id):
        return self.framerobjects[id]

    def add_ahcuhd(self, id, obj):
        self.ahcuhdubjects[id] = obj

    def get_ahcuhd_by_id(self, id):
        return self.ahcuhdubjects[id]



framers = FramerObjects()


# define your own message types
class ApplicationLayerMessageTypes(Enum):
    BROADCAST = "BROADCAST"


# define your own message header structure
class ApplicationLayerMessageHeader(Generics.GenericMessageHeader):
    pass


class UsrpApplicationLayerEventTypes(Enum):
    STARTBROADCAST = "startbroadcast"


class UsrpApplicationLayer(GenericModel):
    def on_init(self, eventobj: GenericEvent):
        self.counter = 0

    def __init__(self, componentname, componentid):
        super().__init__(componentname, componentid)
        self.eventhandlers[UsrpApplicationLayerEventTypes.STARTBROADCAST] = self.on_startbroadcast

    def on_message_from_top(self, eventobj: GenericEvent):
    # print(f"I am {self.componentname}.{self.componentinstancenumber},sending down eventcontent={eventobj.eventcontent}\n")
        self.send_down(GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent))

    def on_message_from_bottom(self, eventobj: GenericEvent):
        evt = GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
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

    def on_startbroadcast(self, eventobj: GenericEvent):
        if self.componentinstancenumber == 1:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 1, 0)
        else:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 0, 1)
        self.counter = self.counter + 1

        payload = "BMSG-" + str(self.counter)
        broadcastmessage = Generics.GenericMessage(hdr, payload)
        evt = GenericEvent(self, Definitions.EventTypes.MFRT, broadcastmessage)
        # time.sleep(3)
        self.send_down(evt)
        #print("Starting broadcast")

mutex = Lock()
def ofdm_callback(header:POINTER(c_ubyte), header_valid:c_uint32, payload:POINTER(c_ubyte), payload_len:c_uint32, payload_valid:c_int32, stats:struct_c__SA_framesyncstats_s, userdata:POINTER(None)):
    mutex.acquire(1)
    try:
        framer = framers.get_framer_by_id(userdata)
        #print("ofdm_callback", framer.componentinstancenumber)
        #ofdmflexframegen_print(framer.fg)
        # userdata.debug_print()
        #print("Type", type(payload), "Payload Valid?: ", payload_valid, "Length=", payload_len, "payload=", bytes(payload))

        if payload_valid != 0:
            #ofdmflexframesync_print(framer.fs)
            pload = string_at(payload, payload_len)
            #print("pload=", pload)
            phymsg = pickle.loads(pload)
            msg = Generics.GenericMessage(phymsg.header, phymsg.payload)
            framer.send_self(GenericEvent(framer, UsrpB210PhyEventTypes.RECV, msg))
            #print("Header=", msg.header.messagetype, " Payload=", msg.payload, " RSSI=", stats.rssi)
        #else:
            #pass
        #print("INVALID Type Node", framer.componentinstancenumber, "Payload Valid:[", payload_valid, "]Length=", payload_len, "payload=", bytes(payload))

    except Exception as e:
        print("Exception_ofdm_callback:", e)
        print("INVALID Type Node", framer.componentinstancenumber, "Payload Valid:[", payload_valid, "]Length=", payload_len, "payload=", bytes(payload))
    mutex.release()
    return 0


class UsrpB210PhyEventTypes(Enum):
  RECV = "recv"


# define your own message header structure
class UsrpB210PhyMessageHeader(Generics.GenericMessageHeader):
    pass


# define your own message payload structure
class UsrpB210PhyMessagePayload(Generics.GenericMessagePayload):

  def __init__(self, header, payload):
    self.phyheader = header
    self.phypayload = payload

class FrameHandlerBase(GenericModel):

    def __init__(self,componentname, componentinstancenumber):
        super().__init__(componentname, componentinstancenumber)

        self.chan = 0
        self.bandwidth = 250000
        self.freq = 2462000000.0
        self.lo_offset = 0
        self.rate = self.bandwidth
        self.hw_tx_gain = 70.0  # hardware tx antenna gain
        self.hw_rx_gain = 20.0  # hardware rx antenna gain
        self.sw_tx_gain = -12.0  # software gain
        self.duration = 1
        self.ahcuhd = AhcUhdUtils(self.componentinstancenumber)
        framers.add_framer(id(self), self)
        # framers.add_ahcuhd(componentinstancenumber, self.ahcuhd )
        self.ahcuhd.configureUsrp("winslab_b210_" + str(self.componentinstancenumber))
        print("Configuring", "winslab_b210_" + str(self.componentinstancenumber))
        self.configure()
        self.eventhandlers[UsrpB210PhyEventTypes.RECV] = self.on_recv

    def on_recv(self, eventobj: GenericEvent):
        #print("Node", self.componentinstancenumber, " Received message type:", eventobj.eventcontent.header.messagetype, "  from ", eventobj.eventcontent.payload.phyheader.messagefrom)

        if eventobj.eventcontent.payload.phyheader.messagefrom != self.componentinstancenumber:
          msg = Generics.GenericMessage(eventobj.eventcontent.payload.phyheader, eventobj.eventcontent.payload.phypayload)
          self.send_up(GenericEvent(self, Definitions.EventTypes.MFRB, msg))




    def on_message_from_top(self, eventobj: GenericEvent):
    # channel receives the input message and will process the message by the process event in the next pipeline stage
    # Preserve the event id through the pipeline

        str_header = "12345678"  #This is the PMD flexframe header. Ourt physical layer header will be concat with the payload below...
        hlen = len(str_header)
        byte_arr_header = bytearray(str_header, 'utf-8')
        header = (c_ubyte * hlen)(*(byte_arr_header))

        hdr = UsrpB210PhyMessageHeader(UsrpB210PhyMessageTypes.PHYFRAMEDATA, self.componentinstancenumber, Definitions.MessageDestinationIdentifiers.LINKLAYERBROADCAST)
        pld = UsrpB210PhyMessagePayload(eventobj.eventcontent.header, eventobj.eventcontent.payload )
        msg = Definitions.GenericMessage(hdr, pld)
        byte_arr_msg = bytearray(pickle.dumps(msg))
        plen = len(byte_arr_msg)
        payload = (c_ubyte * plen)(*(byte_arr_msg))
        payload_len = plen
        #print("bytearry:", byte_arr_msg, "Payload:",payload, " payload_len:", payload_len)
        self.transmit(header, payload, payload_len, LIQUID_MODEM_QPSK, LIQUID_FEC_NONE, LIQUID_FEC_HAMMING74 )  # TODO: Check params
        #print("sentpload=", string_at(payload, payload_len))
        #pload = string_at(payload, payload_len)
        #print("pload=", pload)
        #phymsg = pickle.loads(pload)
        #msg2 = GenericMessage(phymsg.header, phymsg.payload)

class UsrpB210PhyMessageTypes(Enum):
  PHYFRAMEDATA = "PHYFRAMEDATA"


class UsrpB210OfdmFlexFramePhy(FrameHandlerBase):

    def on_init(self, eventobj: GenericEvent):
        #print("initialize LiquidDspOfdmFlexFrameHandler")
        pass

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

class ComponentConfigurationParameters():
    pass

class MacCsmaPPersistentConfigurationParameters (ComponentConfigurationParameters):
    def __init__(self, p):
        self.p = p

class GenericMacEventTypes(Enum):
    HANDLEMACFRAME = "handlemacframe"


class GenericMac(GenericModel):

    def __init__(self, componentname, componentinstancenumber, uhd):
        super().__init__(componentname, componentinstancenumber)
        self.framequeue = queue.Queue()
        self.ahcuhd = uhd
        print("I am Generic MAC my uhd instance id is ", self.ahcuhd.componentinstancenumber)
        self.eventhandlers[GenericMacEventTypes.HANDLEMACFRAME] = self.on_handlemacframe

    def on_init(self, eventobj: GenericEvent):
        self.send_self(GenericEvent(self, GenericMacEventTypes.HANDLEMACFRAME, None))  # Continuously trigger handle_frame
        # print("Initialized", self.componentname, ":", self.componentinstancenumber)

    def on_handlemacframe(self, eventobj: GenericEvent):
        # print("will handle frame from on_handlemacframe")
        self.handle_frame()
        # self.send_self(Event(self, GenericMacEventTypes.HANDLEMACFRAME, None)) #Continuously trigger handle_frame
        # HANDLEMACFRAME event will be generated by the inheriting component to facilitate delay

    def on_message_from_bottom(self, eventobj: GenericEvent):
        # print(f"I am {self.componentname}, eventcontent={eventobj.eventcontent}\n")
        evt = GenericEvent(self, Definitions.EventTypes.MFRB, eventobj.eventcontent)
        self.send_up(evt)

    def on_message_from_top(self, eventobj: GenericEvent):
        # print(f"I am {self.componentname}, eventcontent={eventobj.eventcontent}\n")
        # put message in queue and try accessing the channel
        self.framequeue.put_nowait(eventobj)
        #print("Mac put the frame in queueu", eventobj.eventcontent.payload)

class MacCsmaPPersistent(GenericMac):

    #Constructor
    def __init__(self, componentname, componentinstancenumber, configurationparameters:MacCsmaPPersistentConfigurationParameters, uhd):
        super().__init__(componentname, componentinstancenumber, uhd)
        self.p = configurationparameters.p

    #on_init will be called from topo.start to initialize components
    def on_init(self, eventobj: GenericEvent):
        self.retrialcnt = 0
        super().on_init(eventobj)  # required because of inheritence
        #print("Initialized", self.componentname, ":", self.componentinstancenumber)

    def handle_frame(self):
        #TODO: not a good solution put message in queue, schedule a future event to retry yhe first item in queueu
        #print("handle_frame")
        if self.framequeue.qsize() > 0:
            #print("handle_frame", "queue not empty")
            randval = random.random()
            if randval < self.p: # TODO: Check if correct
                clearmi, powerdb  = self.ahcuhd.ischannelclear(threshold=-35)
                #print("Component:", self.componentinstancenumber, "clear mi=", clearmi, " Power=", powerdb)
                if  clearmi == True:
                    try:
                        eventobj = self.framequeue.get()
                        evt = GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
                        self.send_down(evt)
                        self.retrialcnt = 0
                    except Exception as e:
                        print("MacCsmaPPersistent handle_frame exception, ", e)
                else:
                    self.retrialcnt = self.retrialcnt + 1
                    time.sleep(random.randrange(0,math.pow(2,self.retrialcnt))*0.001)
                    #print("Busy")
        else:
            #print("Queue size", self.framequeue.qsize())
            pass
        time.sleep(0.00001) # TODO: Think about this otherwise we will only do cca
        self.send_self(GenericEvent(self, GenericMacEventTypes.HANDLEMACFRAME, None)) #Continuously trigger handle_frame


class UsrpNode(GenericModel):
    counter = 0
    def on_init(self, eventobj: GenericEvent):
        pass

    def __init__(self, componentname, componentid):
        # SUBCOMPONENTS

        macconfig = MacCsmaPPersistentConfigurationParameters(0.5)

        self.appl = UsrpApplicationLayer("UsrpApplicationLayer", componentid)
        self.phy = UsrpB210OfdmFlexFramePhy("UsrpB210OfdmFlexFramePhy", componentid)
        self.mac = MacCsmaPPersistent("MacCsmaPPersistent", componentid,  configurationparameters=macconfig,uhd=self.phy.ahcuhd)

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
        topo.nodes[1].appl.send_self(GenericEvent(topo.nodes[0], UsrpApplicationLayerEventTypes.STARTBROADCAST, None))
        time.sleep(1)
        i = i + 1


if __name__ == "__main__":
    main()


